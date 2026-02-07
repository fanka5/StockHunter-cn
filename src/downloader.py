import baostock as bs
import pandas as pd
import os
import datetime
import time
from multiprocessing import Pool, freeze_support
from tqdm import tqdm
from typing import List, Tuple, Optional, Any

# 导入配置
from config import (
    DATA_DIR, PROXY_URL, PROCESS_COUNT, MAX_ATTEMPTS,
    ABORT_THRESHOLD, DEFAULT_START_DATE, DATA_READY_HOUR
)


# ===========================
# 辅助函数 (保持在类外部以支持多进程 Pickle)
# ===========================

def get_last_date(file_path: str) -> Optional[str]:
    """高效读取 CSV 最后一行日期"""
    try:
        if os.path.getsize(file_path) < 50:
            return None
        with open(file_path, 'rb') as f:
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
            last_line = f.readline().decode(errors='ignore')
            return last_line.split(',')[0]
    except Exception:
        return None


def set_proxy(enable: bool) -> None:
    if enable and PROXY_URL:
        os.environ["http_proxy"] = PROXY_URL
        os.environ["https_proxy"] = PROXY_URL
    else:
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)


def check_status_worker(item: Tuple[str, str]) -> Tuple[Tuple[str, str], bool, Optional[str], Optional[str]]:
    """预检查 Worker"""
    code, name = item
    safe_name = name.replace("*", "").replace("/", "").replace("?", "")
    file_path = os.path.join(str(DATA_DIR), f"{code}_{safe_name}.csv")

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    start_date = DEFAULT_START_DATE

    # 1. 文件不存在 -> 全量下载
    if not os.path.exists(file_path):
        return (item, True, start_date, 'w')

    last_date = get_last_date(file_path)
    if not last_date:
        return (item, True, start_date, 'w')

    # 2. 判定逻辑
    if last_date >= today_str:
        return (item, False, None, None)

    last_dt = datetime.datetime.strptime(last_date, "%Y-%m-%d")
    yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # 如果最后日期是昨天，且现在还没到下午5点 (收盘数据未出) -> 无需更新
    if last_date == yesterday and current_hour < DATA_READY_HOUR:
        return (item, False, None, None)

    # 计算增量更新的开始日期
    next_dt = last_dt + datetime.timedelta(days=1)
    new_start_date = next_dt.strftime("%Y-%m-%d")

    if new_start_date > today_str:
        return (item, False, None, None)

    # 3. 需要追加下载 (模式设为 'a'，但在 worker 里我们会做去重处理)
    return (item, True, new_start_date, 'a')


def download_worker(args: Tuple[List[Any], bool]) -> Tuple[List[Any], List[Any]]:
    """下载 Worker (包含去重逻辑)"""
    task_list, use_proxy = args
    set_proxy(use_proxy)

    fields = "date,code,open,high,low,close,volume,amount,adjustflag,turn,pctChg"
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    try:
        lg = bs.login()
        if lg.error_code != '0':
            return ([], [t[0] for t in task_list])
    except Exception:
        return ([], [t[0] for t in task_list])

    success = []
    failed = []

    for task in task_list:
        item, _, start_date, mode = task
        code, name = item
        safe_name = name.replace("*", "").replace("/", "").replace("?", "")
        file_path = os.path.join(str(DATA_DIR), f"{code}_{safe_name}.csv")

        try:
            rs = bs.query_history_k_data_plus(
                code, fields,
                start_date=start_date, end_date=today_str,
                frequency="d", adjustflag="2"
            )

            if rs.error_code != '0':
                failed.append(item)
                continue

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            # 只有当获取到了数据才进行写入处理
            if data_list:
                new_df = pd.DataFrame(data_list, columns=rs.fields)

                # 数值转换
                cols_to_numeric = ['open', 'high', 'low', 'close', 'volume', 'pctChg']
                for col in cols_to_numeric:
                    if col in new_df.columns:
                        new_df[col] = pd.to_numeric(new_df[col], errors='coerce').fillna(0)

                # 【关键修复】防止重复追加导致 MA 线乱画
                # 即使原本是 'a' 模式，我们也读取旧文件，合并，去重，再覆盖写入
                if mode == 'a' and os.path.exists(file_path):
                    try:
                        old_df = pd.read_csv(file_path)
                        # 合并
                        final_df = pd.concat([old_df, new_df])
                        # 核心：根据日期去重，保留最后一条
                        final_df.drop_duplicates(subset=['date'], keep='last', inplace=True)
                        final_df.sort_values('date', inplace=True)
                        final_df.to_csv(file_path, index=False)
                    except:
                        # 如果读取旧文件失败，就直接覆盖
                        new_df.to_csv(file_path, index=False)
                else:
                    # 'w' 模式或文件不存在
                    new_df.to_csv(file_path, index=False)

            # 只要没有抛出异常，就算成功（即使 data_list 为空，说明没有新数据，也算任务完成）
            success.append(item)
        except Exception:
            failed.append(item)

    bs.logout()
    return (success, failed)


# ===========================
# 核心类定义
# ===========================

class StockDownloader:
    def __init__(self):
        self.today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    def get_all_stocks(self) -> List[Tuple[str, str]]:
        set_proxy(False)
        bs.login()
        print("📋 正在获取全市场股票列表...")
        stock_list = []
        for i in range(30):
            d = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            rs = bs.query_all_stock(day=d)
            if rs.error_code != '0': continue
            temp = []
            while rs.next(): temp.append(rs.get_row_data())
            if len(temp) > 4000:
                for row in temp:
                    c, n = row[0], row[2]
                    if c.startswith(("sh.6", "sz.0", "sz.3", "bj.")):
                        stock_list.append((c, n))
                break
        bs.logout()
        return stock_list

    def _get_watchlist_stocks(self, watchlist_codes: List[str]) -> List[Tuple[str, str]]:
        tasks = []
        local_map = {}
        data_dir_str = str(DATA_DIR)
        if os.path.exists(data_dir_str):
            for f in os.listdir(data_dir_str):
                if f.endswith(".csv"):
                    try:
                        raw_name = f.replace(".csv", "")
                        parts = raw_name.split("_")
                        if len(parts) >= 2: local_map[parts[0]] = parts[1]
                    except:
                        continue
        for code in watchlist_codes:
            name = local_map.get(code, "自选股")
            tasks.append((code, name))
        return tasks

    def run(self, target_codes: Optional[List[str]] = None):
        freeze_support()
        print(f"--- StockHunter 数据同步引擎 ---")

        tasks_to_run = []
        skipped_count = 0

        # 1. 确定列表
        if target_codes:
            print(f"⚡ 极速模式：仅更新 {len(target_codes)} 只自选股")
            all_stocks = self._get_watchlist_stocks(target_codes)
        else:
            all_stocks = self.get_all_stocks()

        if not all_stocks:
            print("❌ 没有获取到股票列表")
            return

        # 2. 预检
        print(f"\n🔍 预检本地文件状态...")
        pool_size = 4 if target_codes else 8

        with Pool(processes=pool_size) as pool:
            results = pool.map(check_status_worker, all_stocks)

        for res in results:
            item, need_dl, start, mode = res
            if need_dl:
                tasks_to_run.append((item, need_dl, start, mode))
            else:
                skipped_count += 1

        print(f"⏭️  已跳过: {skipped_count} | 📥 待下载: {len(tasks_to_run)}")

        if not tasks_to_run:
            print("✅ 数据已是最新")
            return

        # 3. 下载循环
        pending_tasks = tasks_to_run
        final_success_count = 0

        # 建立一个集合来记录已经完成的 code (避免依赖磁盘校验)
        finished_codes = set()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            # 过滤掉已经成功的任务
            current_batch = [t for t in pending_tasks if t[0][0] not in finished_codes]
            if not current_batch: break

            use_proxy = (attempt % 2 == 0)
            proxy_msg = f"代理模式" if use_proxy and PROXY_URL else "直连模式"
            print(f"\n🔄 [第 {attempt}/{MAX_ATTEMPTS} 次] {proxy_msg} | 剩余: {len(current_batch)}")

            chunk_size = 20
            chunks = []
            for i in range(0, len(current_batch), chunk_size):
                chunks.append((current_batch[i:i + chunk_size], use_proxy))

            consecutive_fail = 0
            abort = False

            with Pool(processes=PROCESS_COUNT) as pool:
                with tqdm(total=len(current_batch), desc="进度", unit="只") as pbar:
                    for success_list, failed_list in pool.imap_unordered(download_worker, chunks):
                        pbar.update(len(success_list) + len(failed_list))

                        # 【核心修复】直接使用 worker 返回的成功列表
                        for item in success_list:
                            finished_codes.add(item[0])  # item[0] is code
                            final_success_count += 1

                        if success_list:
                            consecutive_fail = 0
                        else:
                            consecutive_fail += len(failed_list)

                        if consecutive_fail >= ABORT_THRESHOLD:
                            abort = True
                            pool.terminate()
                            break

            if abort:
                print(f"⚠️  触发熔断")
                break

            if len(finished_codes) < len(tasks_to_run) and attempt < MAX_ATTEMPTS:
                time.sleep(3)

        print(f"\n✅ 更新完成! 本次下载: {final_success_count}")


if __name__ == "__main__":
    try:
        downloader = StockDownloader()
        downloader.run()
    except ImportError:
        pass
