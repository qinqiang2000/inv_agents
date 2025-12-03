#!/usr/bin/env python3
"""
发票数据导出脚本 - 高性能Python版本
从t_invoice表中批量导出开票成功的发票数据，按租户和国家组织存储
使用JSON_ARRAYAGG批量查询和多线程处理，大幅提升导出性能
"""

import pymysql
import json
import os
import sys
import logging
import argparse
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import gzip
import shutil
from tqdm import tqdm

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
OUTPUT_BASE_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'context' / 'invoices'))


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
                 compress: bool = False, dry_run: bool = False):
        self.output_dir = Path(output_dir or OUTPUT_BASE_DIR)
        self.num_threads = num_threads
        self.compress = compress
        self.dry_run = dry_run
        self.stats = {
            'total_groups': 0,
            'total_invoices': 0,
            'successful_files': 0,
            'failed_files': 0,
            'start_time': None,
            'end_time': None
        }
        self.lock = threading.Lock()

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
        logger.info("获取租户-国家分组信息...")

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

        logger.info(f"找到 {len(formatted_results)} 个租户-国家分组")
        self.stats['total_groups'] = len(formatted_results)
        return formatted_results

    def get_invoices_for_group(self, connection, tenant_id: str, country: str) -> List[Dict]:
        """获取指定租户-国家的发票数据"""
        country_filter = f"fcountry = '{country}'" if country != 'UNKNOWN' else "fcountry IS NULL OR fcountry = ''"

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

        # 创建目录结构
        tenant_dir = self.output_dir / tenant_id
        country_dir = tenant_dir / country
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

    def process_group(self, connection, tenant_id: str, country: str, invoice_count: int,
                     progress_bar: tqdm = None) -> Dict[str, Any]:
        """处理单个租户-国家分组"""
        thread_name = threading.current_thread().name
        start_time = time.time()

        try:
            logger.info(f"[{thread_name}] 开始处理租户 {tenant_id} 国家 {country} ({invoice_count} 条记录)")

            # 获取发票数据
            invoices = self.get_invoices_for_group(connection, tenant_id, country)

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
        finally:
            if progress_bar:
                progress_bar.update(1)

    def export_all(self, limit_groups: int = None) -> bool:
        """导出所有发票数据"""
        logger.info("=" * 80)
        logger.info("发票数据导出开始 (高性能Python版本)")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"线程数: {self.num_threads}")
        logger.info(f"压缩输出: {self.compress}")
        logger.info(f"试运行模式: {self.dry_run}")
        logger.info("=" * 80)

        self.stats['start_time'] = time.time()

        try:
            with DatabaseConnection(DB_CONFIG) as conn:
                # 获取所有分组
                groups = self.get_tenant_country_groups(conn)

                if limit_groups:
                    groups = groups[:limit_groups]
                    logger.info(f"限制处理前 {limit_groups} 个分组")

                # 使用多线程处理
                results = []
                with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                    # 创建进度条
                    with tqdm(total=len(groups), desc="处理分组", unit="group") as progress_bar:
                        # 提交所有任务
                        future_to_group = {
                            executor.submit(
                                self.process_group,
                                conn,
                                tenant_id,
                                country,
                                invoice_count,
                                progress_bar
                            ): (tenant_id, country)
                            for tenant_id, country, invoice_count in groups
                        }

                        # 收集结果
                        for future in as_completed(future_to_group):
                            result = future.result()
                            results.append(result)

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

                return failed_groups == 0

        except Exception as e:
            logger.error(f"导出失败: {e}", exc_info=True)
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='发票数据导出脚本')
    parser.add_argument('--output-dir', '-o', help='输出目录')
    parser.add_argument('--threads', '-t', type=int, default=4, help='线程数')
    parser.add_argument('--compress', '-c', action='store_true', help='启用gzip压缩')
    parser.add_argument('--dry-run', '-d', action='store_true', help='试运行模式')
    parser.add_argument('--limit', '-l', type=int, help='限制处理的分组数量（用于测试）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    exporter = InvoiceExporter(
        output_dir=args.output_dir,
        num_threads=args.threads,
        compress=args.compress,
        dry_run=args.dry_run
    )

    success = exporter.export_all(limit_groups=args.limit)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()