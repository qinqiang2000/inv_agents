#!/usr/bin/env python3
"""
发票数据导出脚本 - 高性能Python版本
从t_invoice表中批量导出开票成功的发票数据，按租户和国家组织存储
使用JSON_ARRAYAGG批量查询和多线程处理，大幅提升导出性能
支持全量导出和增量导出两种模式
"""

import pymysql
import json
import os
import sys
import logging
import argparse
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import gzip
import shutil
from tqdm import tqdm
import fcntl

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'jump-test.piaozone.com'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'rnd'),
    'password': os.getenv('DB_PASSWORD', 'ZaFOjoFp&SdB8bum'),
    'database': os.getenv('DB_NAME', 'test_jin'),
    'charset': 'utf8mb4',
    'connect_timeout': 60,
    'read_timeout': 300,
    'write_timeout': 300,
    'autocommit': True,
    'cursorclass': pymysql.cursors.DictCursor
}

# 输出目录配置
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_BASE_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'tenant-data'))

# 增量导出配置
TIME_BUFFER_SECONDS = 300  # 5分钟安全边界，避免捕获正在进行的事务
STATE_FILE_DIR = Path(OUTPUT_BASE_DIR) / '.export_state'
STATE_FILE = STATE_FILE_DIR / '.last_export_time'
LOCK_FILE = STATE_FILE_DIR / '.export.lock'


class StateManager:
    """增量导出状态管理"""

    def __init__(self, lock_path: Path = None):
        self.lock_path = lock_path or LOCK_FILE
        self.lock_file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_lock()

    def acquire_lock(self) -> bool:
        """获取导出锁"""
        try:
            STATE_FILE_DIR.mkdir(parents=True, exist_ok=True)
            self.lock_file = open(self.lock_path, 'w')
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.info("已获取导出锁")
            return True
        except (OSError, IOError):
            logger.error(f"另一个导出进程正在运行(锁文件: {self.lock_path})")
            logger.error(f"如果确认没有其他进程，请手动删除锁文件: rm -rf {self.lock_path}")
            return False

    def release_lock(self):
        """释放导出锁"""
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                if self.lock_path.exists():
                    self.lock_path.unlink()
                logger.info("已释放导出锁")
            except (OSError, IOError):
                pass

    def init_state_file(self):
        """初始化状态文件"""
        STATE_FILE_DIR.mkdir(parents=True, exist_ok=True)

        if not STATE_FILE.exists():
            logger.info(f"创建状态文件: {STATE_FILE}")
            STATE_FILE.touch()

        # 验证状态文件格式
        if STATE_FILE.stat().st_size > 0:
            try:
                with open(STATE_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not re.match(r'^\d+\|\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\d+|[A-Z]+$', line):
                            logger.warning("状态文件格式不正确，将备份后重新创建")
                            backup_file = STATE_FILE.with_suffix(f'.backup.{int(time.time())}')
                            shutil.move(STATE_FILE, backup_file)
                            STATE_FILE.touch()
                            break
            except Exception as e:
                logger.warning(f"验证状态文件时出错: {e}")

    def get_last_export_time(self, tenant_id: str) -> str:
        """获取租户的上次导出时间"""
        if not STATE_FILE.exists():
            return ""

        try:
            with open(STATE_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{tenant_id}|"):
                        return line.split('|')[1]
        except Exception as e:
            logger.error(f"读取状态文件失败: {e}")

        return ""

    def update_export_time(self, tenant_id: str, export_time: str, record_count: int, status: str = "SUCCESS"):
        """更新租户的导出时间"""
        if hasattr(self, 'dry_run') and self.dry_run:
            logger.info(f"[DRY RUN] 将更新状态: 租户{tenant_id} -> {export_time} ({record_count}条)")
            return

        temp_file = STATE_FILE.with_suffix('.tmp')

        try:
            # 移除旧记录并添加新记录
            if STATE_FILE.exists():
                with open(STATE_FILE, 'r') as f:
                    lines = f.readlines()

                with open(temp_file, 'w') as f:
                    for line in lines:
                        if not line.strip().startswith(f"{tenant_id}|"):
                            f.write(line)

            new_line = f"{tenant_id}|{export_time}|{record_count}|{status}\n"
            with open(temp_file, 'a') as f:
                f.write(new_line)

            # 原子替换
            shutil.move(temp_file, STATE_FILE)

        except Exception as e:
            logger.error(f"更新状态文件失败: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def backup_state_file(self):
        """备份状态文件"""
        if STATE_FILE.exists() and STATE_FILE.stat().st_size > 0:
            backup_file = STATE_FILE.with_suffix(f'.backup.{int(time.time())}')
            shutil.copy2(STATE_FILE, backup_file)
            logger.info(f"状态文件已备份到: {backup_file}")

    def calculate_export_boundary(self) -> str:
        """计算导出安全边界时间(当前时间 - 5分钟)"""
        boundary_time = datetime.now(timezone.utc) - timedelta(seconds=TIME_BUFFER_SECONDS)
        return boundary_time.strftime('%Y-%m-%d %H:%M:%S')


class DatabaseConnection:
    """数据库连接管理"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection = None

    def __enter__(self):
        self.connection = pymysql.connect(**self.config)
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()


class InvoiceExporter:
    """发票数据导出器"""

    def __init__(self, output_dir: str = None, num_threads: int = 4,
                 compress: bool = False, dry_run: bool = False, incremental: bool = False,
                 tenant_id: str = None, log_queue=None, progress_queue=None):
        self.output_dir = Path(output_dir or OUTPUT_BASE_DIR)
        self.num_threads = num_threads
        self.compress = compress
        self.dry_run = dry_run
        self.incremental = incremental
        self.tenant_id = tenant_id
        self.log_queue = log_queue
        self.progress_queue = progress_queue
        self.stats = {
            'total_groups': 0,
            'total_invoices': 0,
            'successful_files': 0,
            'failed_files': 0,
            'start_time': None,
            'end_time': None
        }
        self.lock = threading.Lock()
        self.state_manager = StateManager()
        self.state_manager.dry_run = dry_run

        # Setup queue logging if provided
        if self.log_queue:
            try:
                # Import here to avoid issues when running as CLI
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent / 'api' / 'admin'))
                from logging_handler import QueueLoggingHandler

                queue_handler = QueueLoggingHandler(self.log_queue)
                queue_handler.setLevel(logging.INFO)
                logger.addHandler(queue_handler)
            except Exception as e:
                logger.warning(f"Failed to setup queue logging: {e}")

    def validate_json_field(self, json_str: str) -> bool:
        """验证JSON字段格式"""
        if not json_str or not json_str.strip():
            return False

        try:
            data = json.loads(json_str)
            # 检查必要字段
            required_fields = ['ID', 'IssueDate']
            for field in required_fields:
                if field not in data:
                    return False
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    def clean_filename(self, filename: str) -> str:
        """清理文件名，替换不合法字符"""
        # 替换文件名中的特殊字符
        return re.sub(r'[\\/:"*?<>|]', '_', filename)

    def get_tenant_country_groups(self, connection) -> List[Tuple[str, str, int]]:
        """获取租户-国家分组信息"""
        if self.tenant_id:
            logger.info(f"获取租户 {self.tenant_id} 的国家分组信息...")
        else:
            logger.info("获取所有租户-国家分组信息...")

        sql = """
            SELECT
                ftenant_id,
                IFNULL(fcountry, 'UNKNOWN') as fcountry,
                COUNT(*) as invoice_count
            FROM t_invoice
            WHERE fissue_status = 3
              AND fext_field IS NOT NULL
              AND LENGTH(fext_field) > 0
              AND finvoice_no IS NOT NULL
              AND LENGTH(finvoice_no) > 0
              AND fissue_date IS NOT NULL
        """

        # 添加租户过滤条件
        if self.tenant_id:
            sql += f"  AND ftenant_id = '{self.tenant_id}'"

        sql += """
            GROUP BY ftenant_id, fcountry
            ORDER BY ftenant_id, fcountry
        """

        with connection.cursor() as cursor:
            cursor.execute(sql)
            results = cursor.fetchall()

        # 转换字典格式为元组格式
        formatted_results = []
        for row in results:
            formatted_results.append((
                row['ftenant_id'],
                row['fcountry'],
                row['invoice_count']
            ))

        if self.tenant_id:
            logger.info(f"租户 {self.tenant_id} 找到 {len(formatted_results)} 个国家分组")
        else:
            logger.info(f"找到 {len(formatted_results)} 个租户-国家分组")
        self.stats['total_groups'] = len(formatted_results)
        return formatted_results

    def get_invoices_for_group(self, connection, tenant_id: str, country: str,
                               last_time: str = None, boundary_time: str = None) -> List[Dict]:
        """获取指定租户-国家的发票数据"""
        country_filter = f"fcountry = '{country}'" if country != 'UNKNOWN' else "fcountry IS NULL OR fcountry = ''"

        if self.incremental and last_time and boundary_time:
            # 增量模式: 添加时间过滤
            sql = f"""
                SELECT
                    finvoice_no,
                    DATE_FORMAT(fissue_date, '%Y%m%d') as issue_date_formatted,
                    fext_field,
                    fupdate_time
                FROM t_invoice
                WHERE fissue_status = 3
                  AND ftenant_id = '{tenant_id}'
                  AND ({country_filter})
                  AND fext_field IS NOT NULL
                  AND LENGTH(fext_field) > 0
                  AND finvoice_no IS NOT NULL
                  AND LENGTH(finvoice_no) > 0
                  AND fissue_date IS NOT NULL
                  AND fupdate_time > '{last_time}'
                  AND fupdate_time <= '{boundary_time}'
                ORDER BY fupdate_time ASC, finvoice_no ASC
            """
        else:
            # 全量模式: 原有查询
            sql = f"""
                SELECT
                    finvoice_no,
                    DATE_FORMAT(fissue_date, '%Y%m%d') as issue_date_formatted,
                    fext_field,
                    fupdate_time
                FROM t_invoice
                WHERE fissue_status = 3
                  AND ftenant_id = '{tenant_id}'
                  AND ({country_filter})
                  AND fext_field IS NOT NULL
                  AND LENGTH(fext_field) > 0
                  AND finvoice_no IS NOT NULL
                  AND LENGTH(finvoice_no) > 0
                  AND fissue_date IS NOT NULL
                ORDER BY fissue_date, finvoice_no
            """

        with connection.cursor() as cursor:
            cursor.execute(sql)
            results = cursor.fetchall()

        invoices = []
        for i, row in enumerate(results):
            try:
                # DictCursor返回的是字典格式
                invoice_no = row['finvoice_no']
                issue_date = row['issue_date_formatted']
                ext_field = row['fext_field']
                update_time = row['fupdate_time']

                # 验证必要字段
                if not invoice_no or not ext_field:
                    logger.warning(f"跳过缺少必要字段的记录 {i}: invoice_no={invoice_no}, ext_field长度={len(ext_field) if ext_field else 0}")
                    continue

                # 验证JSON字段
                if not self.validate_json_field(ext_field):
                    logger.warning(f"跳过无效的JSON字段: {invoice_no}")
                    continue

                invoices.append({
                    'invoice_no': invoice_no,
                    'issue_date': issue_date,
                    'ext_field': json.loads(ext_field),
                    'update_time': update_time.isoformat() if update_time else None
                })
            except Exception as e:
                logger.error(f"处理第 {i} 条记录失败: {e}")
                continue

        return invoices

    def write_invoice_files(self, tenant_id: str, country: str, invoices: List[Dict]) -> int:
        """写入发票文件"""
        if self.dry_run:
            logger.info(f"[DRY RUN] 将写入 {len(invoices)} 个文件到 {tenant_id}/{country}/")
            return len(invoices)

        # 创建目录结构: tenant-data/{tenant_id}/invoices/{country}/
        tenant_dir = self.output_dir / tenant_id
        invoices_dir = tenant_dir / "invoices"
        country_dir = invoices_dir / country
        country_dir.mkdir(parents=True, exist_ok=True)

        successful_count = 0
        for invoice in invoices:
            try:
                # 生成文件名
                safe_invoice_no = self.clean_filename(invoice['invoice_no'])
                filename = f"{invoice['issue_date']}+{safe_invoice_no}.json"

                if self.compress:
                    filename += '.gz'
                    filepath = country_dir / filename

                    # 写入压缩文件
                    with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                        json.dump(invoice['ext_field'], f, ensure_ascii=False, indent=2)
                else:
                    filepath = country_dir / filename

                    # 写入普通文件
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(invoice['ext_field'], f, ensure_ascii=False, indent=2)

                successful_count += 1

            except Exception as e:
                logger.error(f"写入文件失败 {invoice['invoice_no']}: {e}")
                with self.lock:
                    self.stats['failed_files'] += 1

        return successful_count

    def process_group(self, tenant_id: str, country: str, invoice_count: int,
                     last_time: str = None, boundary_time: str = None) -> Dict[str, Any]:
        """处理单个租户-国家分组"""
        thread_name = threading.current_thread().name
        start_time = time.time()

        try:
            if self.incremental:
                time_range = f" ({last_time} -> {boundary_time})"
            else:
                time_range = ""

            logger.info(f"[{thread_name}] 开始处理租户 {tenant_id} 国家 {country}{time_range}")

            # 每个线程创建独立的数据库连接
            with DatabaseConnection(DB_CONFIG) as conn:
                # 获取发票数据
                invoices = self.get_invoices_for_group(conn, tenant_id, country, last_time, boundary_time)

                if not invoices:
                    logger.warning(f"[{thread_name}] 租户 {tenant_id} 国家 {country} 没有有效数据")
                    return {
                        'tenant_id': tenant_id,
                        'country': country,
                        'status': 'no_data',
                        'processed': 0,
                        'duration': time.time() - start_time
                    }

                # 写入文件
                successful_count = self.write_invoice_files(tenant_id, country, invoices)

                duration = time.time() - start_time
                logger.info(f"[{thread_name}] 完成租户 {tenant_id} 国家 {country}: {successful_count}/{len(invoices)} 文件 ({duration:.2f}s)")

                # 更新统计信息
                with self.lock:
                    self.stats['total_invoices'] += len(invoices)
                    self.stats['successful_files'] += successful_count

                return {
                    'tenant_id': tenant_id,
                    'country': country,
                    'status': 'success',
                    'processed': successful_count,
                    'total': len(invoices),
                    'duration': duration
                }

        except Exception as e:
            logger.error(f"[{thread_name}] 处理租户 {tenant_id} 国家 {country} 失败: {e}")
            return {
                'tenant_id': tenant_id,
                'country': country,
                'status': 'error',
                'error': str(e),
                'duration': time.time() - start_time
            }

    def export_incremental(self, limit_groups: int = None) -> bool:
        """增量导出所有发票数据"""
        logger.info("=" * 80)
        if self.tenant_id:
            logger.info(f"发票增量导出开始 - 租户: {self.tenant_id}")
        else:
            logger.info("发票增量导出开始")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"线程数: {self.num_threads}")
        logger.info(f"压缩输出: {self.compress}")
        logger.info(f"试运行模式: {self.dry_run}")
        logger.info("=" * 80)

        # 初始化状态文件和获取锁
        self.state_manager.init_state_file()

        with self.state_manager:
            self.stats['start_time'] = time.time()

            try:
                with DatabaseConnection(DB_CONFIG) as conn:
                    # 计算安全边界时间
                    export_boundary = self.state_manager.calculate_export_boundary()
                    logger.info(f"导出时间边界: {export_boundary}")

                    # 获取所有租户列表
                    logger.info("获取所有租户列表...")
                    all_groups = self.get_tenant_country_groups(conn)

                    if limit_groups:
                        all_groups = all_groups[:limit_groups]
                        logger.info(f"限制处理前 {limit_groups} 个分组")

                    total_export_count = 0
                    total_tenant_count = 0

                    # 获取唯一租户列表
                    unique_tenants = sorted(set(group[0] for group in all_groups))

                    # 逐租户处理
                    for tenant_id in unique_tenants:
                        total_tenant_count += 1

                        # 获取上次导出时间
                        last_time = self.state_manager.get_last_export_time(tenant_id)
                        if not last_time:
                            last_time = "1970-01-01 00:00:00"
                            logger.info(f"租户 {tenant_id}: 首次导出，基线时间: {last_time}")

                        logger.info(f"租户 {tenant_id}: {last_time} -> {export_boundary}")

                        # 处理租户下的所有国家
                        tenant_groups = [(tid, cntry, count) for tid, cntry, count in all_groups
                                         if tid == tenant_id]

                        tenant_export_count = 0
                        tenant_error_count = 0
                        tenant_start_time = time.time()

                        for tid, cntry, count in tenant_groups:
                            # 处理每个国家分组
                            result = self.process_group(
                                tid, cntry, count,
                                last_time=last_time, boundary_time=export_boundary
                            )

                            if result['status'] == 'success':
                                tenant_export_count += result['processed']
                            else:
                                tenant_error_count += 1

                        # 更新状态(即使记录数为0也要更新，表示已同步到边界时间)
                        self.state_manager.update_export_time(tenant_id, export_boundary, tenant_export_count, "SUCCESS")

                        if tenant_export_count > 0:
                            logger.info(f"租户 {tenant_id}: 导出 {tenant_export_count} 条新记录 (耗时: {time.time() - tenant_start_time:.2f}s)")
                        else:
                            logger.info(f"租户 {tenant_id}: 无新增数据")

                        total_export_count += tenant_export_count

                    # 输出统计信息
                    self.stats['end_time'] = time.time()
                    total_duration = self.stats['end_time'] - self.stats['start_time']
                    self.stats['total_invoices'] = total_export_count

                    logger.info("=" * 80)
                    logger.info("增量导出完成!")
                    logger.info("=" * 80)
                    logger.info(f"处理租户数: {total_tenant_count}")
                    logger.info(f"成功导出: {total_export_count} 条新记录")
                    logger.info(f"总耗时: {total_duration:.2f} 秒")
                    logger.info(f"输出目录: {self.output_dir}")
                    logger.info(f"状态文件: {STATE_FILE}")
                    logger.info("=" * 80)

                    # Return summary dict
                    return {
                        "success": True,
                        "total_tenants": total_tenant_count,
                        "new_invoices": total_export_count,
                        "duration_seconds": total_duration,
                        "output_dir": str(self.output_dir),
                        "state_file": str(STATE_FILE)
                    }

            except Exception as e:
                logger.error(f"增量导出失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "duration_seconds": time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
                }

    def export_all(self, limit_groups: int = None) -> bool:
        """导出所有发票数据"""
        logger.info("=" * 80)
        if self.tenant_id:
            logger.info(f"发票数据导出开始 (高性能Python版本) - 租户: {self.tenant_id}")
        else:
            logger.info("发票数据导出开始 (高性能Python版本)")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"线程数: {self.num_threads}")
        logger.info(f"压缩输出: {self.compress}")
        logger.info(f"试运行模式: {self.dry_run}")
        logger.info("=" * 80)

        self.stats['start_time'] = time.time()

        try:
            # 先获取所有分组（使用临时连接）
            with DatabaseConnection(DB_CONFIG) as conn:
                groups = self.get_tenant_country_groups(conn)

            if limit_groups:
                groups = groups[:limit_groups]
                logger.info(f"限制处理前 {limit_groups} 个分组")

            # 使用多线程处理（每个线程创建自己的连接）
            results = []
            completed_count = 0
            total_count = len(groups)

            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                # 提交所有任务
                future_to_group = {
                    executor.submit(
                        self.process_group,
                        tenant_id,
                        country,
                        invoice_count,
                        None  # No tqdm progress bar
                    ): (tenant_id, country)
                    for tenant_id, country, invoice_count in groups
                }

                # 收集结果
                for future in as_completed(future_to_group):
                    result = future.result()
                    results.append(result)

                    # Update progress via queue if provided
                    completed_count += 1
                    if self.progress_queue:
                        try:
                            self.progress_queue.put_nowait({
                                "current": completed_count,
                                "total": total_count,
                                "percentage": (completed_count / total_count) * 100,
                                "message": f"Processed {completed_count}/{total_count} groups"
                            })
                        except Exception:
                            pass  # Ignore queue errors

            # 统计结果
            successful_groups = sum(1 for r in results if r['status'] == 'success')
            failed_groups = sum(1 for r in results if r['status'] == 'error')
            no_data_groups = sum(1 for r in results if r['status'] == 'no_data')

            self.stats['end_time'] = time.time()
            total_duration = self.stats['end_time'] - self.stats['start_time']

            # 输出统计信息
            logger.info("=" * 80)
            logger.info("导出完成!")
            logger.info("=" * 80)
            logger.info(f"总分组数: {len(groups)}")
            logger.info(f"成功分组: {successful_groups}")
            logger.info(f"失败分组: {failed_groups}")
            logger.info(f"无数据分组: {no_data_groups}")
            logger.info(f"总发票数: {self.stats['total_invoices']}")
            logger.info(f"成功文件: {self.stats['successful_files']}")
            logger.info(f"失败文件: {self.stats['failed_files']}")
            logger.info(f"总耗时: {total_duration:.2f} 秒")

            if self.stats['total_invoices'] > 0:
                avg_time = total_duration / self.stats['total_invoices']
                logger.info(f"平均每张发票处理时间: {avg_time:.3f} 秒")

            logger.info(f"输出目录: {self.output_dir}")
            logger.info("=" * 80)

            # Return summary dict instead of bool
            return {
                "success": failed_groups == 0,
                "total_groups": len(groups),
                "successful_groups": successful_groups,
                "failed_groups": failed_groups,
                "no_data_groups": no_data_groups,
                "total_invoices": self.stats['total_invoices'],
                "successful_files": self.stats['successful_files'],
                "failed_files": self.stats['failed_files'],
                "duration_seconds": total_duration,
                "output_dir": str(self.output_dir)
            }

        except Exception as e:
            logger.error(f"导出失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
            }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='发票数据导出脚本')
    parser.add_argument('--output-dir', '-o', help='输出目录')
    parser.add_argument('--threads', '-t', type=int, default=4, help='线程数')
    parser.add_argument('--compress', '-c', action='store_true', help='启用gzip压缩')
    parser.add_argument('--dry-run', '-d', action='store_true', help='试运行模式')
    parser.add_argument('--limit', '-l', type=int, help='限制处理的分组数量（用于测试）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志')
    parser.add_argument('--incremental', '-i', action='store_true', help='增量导出模式')
    parser.add_argument('--tid', type=str, help='指定租户ID进行导出')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    exporter = InvoiceExporter(
        output_dir=args.output_dir,
        num_threads=args.threads,
        compress=args.compress,
        dry_run=args.dry_run,
        incremental=args.incremental,
        tenant_id=args.tid
    )

    # 备份状态文件
    if args.incremental and not args.dry_run:
        exporter.state_manager.backup_state_file()

    # 根据模式执行
    if args.incremental:
        result = exporter.export_incremental(limit_groups=args.limit)
    else:
        result = exporter.export_all(limit_groups=args.limit)

    # Exit based on success status
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()