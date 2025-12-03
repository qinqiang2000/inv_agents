#!/usr/bin/env python3
"""
基础数据导出脚本 - 使用 MySQL JSON_ARRAYAGG 功能
从数据库导出基础数据到 JSON 文件，按国家分组
"""

import pymysql
import json
import os
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
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
    'charset': 'utf8mb4'
}

# 输出目录配置
# 获取脚本所在目录的绝对路径，然后构建输出目录
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_BASE_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_ROOT / 'context' / 'basic-data'))

# 代码类型映射
CODE_TYPES = {
    '0001': {'key': 'uomCodes', 'name': 'UOM代码', 'dir': 'uom-codes'},
    '0003': {'key': 'industryCodes', 'name': '行业代码', 'dir': 'industry-codes'},
    '0004': {'key': 'paymentMeans', 'name': '支付方式', 'dir': 'payment-means'},
    '0005': {'key': 'allowanceReasonCodes', 'name': '折扣/费用原因代码', 'dir': 'allowance-reason-codes'},
    '0006': {'key': 'chargeCodes', 'name': '费用代码', 'dir': 'charge-codes'},
    '0007': {'key': 'dutyTaxFeeCategoryCodes', 'name': '税费类别代码', 'dir': 'duty-tax-fee-category-codes'},
    '0008': {'key': 'taxCategoryCodes', 'name': '税种类别代码', 'dir': 'tax-category-codes'},
    '0009': {'key': 'taxExemptionReasonCodes', 'name': '免税原因代码', 'dir': 'tax-exemption-reason-codes'}
}


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


def check_mysql_version(connection) -> bool:
    """检查 MySQL 版本是否支持 JSON_ARRAYAGG"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        logger.info(f"MySQL 版本: {version}")

        # 解析版本号
        version_parts = version.split('.')
        major = int(version_parts[0])
        minor = int(version_parts[1])

        # MySQL 5.7.22+ 或 8.0+ 支持 JSON_ARRAYAGG
        if major > 5 or (major == 5 and minor >= 7):
            return True
        else:
            logger.error(f"MySQL 版本 {version} 不支持 JSON_ARRAYAGG，需要 5.7.22+ 或 8.0+")
            return False


def export_codes_by_country(connection, code_type: str, code_info: Dict[str, str]) -> int:
    """
    按国家导出代码数据

    Args:
        connection: 数据库连接
        code_type: 代码类型 (e.g., '0001')
        code_info: 代码信息字典

    Returns:
        导出的文件数量
    """
    logger.info(f"开始导出 {code_info['name']} (代码类型: {code_type})...")

    # 创建输出目录
    output_dir = Path(OUTPUT_BASE_DIR) / 'codes' / code_info['dir']
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取所有国家列表
    countries_sql = f"""
        SELECT DISTINCT fcountry
        FROM t_code_info
        WHERE factive = 1
          AND fdelete = 1
          AND fcode_type = '{code_type}'
        ORDER BY fcountry
    """

    with connection.cursor() as cursor:
        cursor.execute(countries_sql)
        countries = [row[0] if row[0] else 'global' for row in cursor.fetchall()]

    logger.info(f"找到 {len(countries)} 个国家/地区")

    # 2. 按国家导出
    file_count = 0
    total_records = 0

    for country in countries:
        country_filter = f"fcountry = '{country}'" if country != 'global' else "fcountry IS NULL OR fcountry = ''"

        # 使用 JSON_ARRAYAGG 生成 JSON
        export_sql = f"""
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'id', fid,
                    'country', fcountry,
                    'codeType', fcode_type,
                    'code', fcode,
                    'name', fname,
                    'description', IFNULL(fdesc, ''),
                    'isSystem', fsystem,
                    'active', factive
                )
            ) AS json_data
            FROM t_code_info
            WHERE factive = 1
              AND fdelete = 1
              AND fcode_type = '{code_type}'
              AND ({country_filter})
            ORDER BY fcode
        """

        with connection.cursor() as cursor:
            cursor.execute(export_sql)
            result = cursor.fetchone()

            if result and result[0]:
                # 解析 JSON 数据
                codes_data = json.loads(result[0])
                record_count = len(codes_data)

                if record_count > 0:
                    # 构建输出数据
                    output_data = {
                        "meta": {
                            "exportTime": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                            "recordCount": record_count,
                            "scope": "country",
                            "country": country,
                            "codeType": code_type
                        },
                        code_info['key']: codes_data
                    }

                    # 写入文件
                    output_file = output_dir / f"{country}.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, indent=2, ensure_ascii=False)

                    logger.info(f"  {country}: {record_count} 条记录 -> {output_file}")
                    file_count += 1
                    total_records += record_count

    logger.info(f"✓ {code_info['name']} 导出完成: {file_count} 个文件, 共 {total_records} 条记录")
    return file_count


def export_global_currencies(connection) -> bool:
    """导出货币数据"""
    logger.info("开始导出货币数据...")

    output_dir = Path(OUTPUT_BASE_DIR) / 'global'
    output_dir.mkdir(parents=True, exist_ok=True)

    sql = """
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'code', fcurrency_code,
                'name', fname,
                'englishName', fenglish_name,
                'symbol', fsymbol,
                'unitPrecision', funit_precision,
                'amountPrecision', famount_precision
            )
        ) AS json_data
        FROM t_currency
        ORDER BY fcurrency_code
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        result = cursor.fetchone()

        if result and result[0]:
            currencies = json.loads(result[0])

            output_data = {
                "meta": {
                    "exportTime": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    "recordCount": len(currencies),
                    "scope": "global"
                },
                "currencies": currencies
            }

            output_file = output_dir / "currencies.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✓ 货币数据导出完成: {len(currencies)} 条记录 -> {output_file}")
            return True

    logger.warning("未找到货币数据")
    return False


def export_global_invoice_types(connection) -> bool:
    """导出发票类型数据"""
    logger.info("开始导出发票类型数据...")

    output_dir = Path(OUTPUT_BASE_DIR) / 'global'
    output_dir.mkdir(parents=True, exist_ok=True)

    sql = """
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'id', fid,
                'invoiceCode', finvoice_code,
                'descriptionEn', IFNULL(fdescription_en, ''),
                'descriptionCn', IFNULL(fdescription_cn, ''),
                'selfbilled', fselfbilled,
                'taxType', ftax_type,
                'countryName', fcountry_name,
                'countryCode', fcountry_code,
                'active', factive,
                'createTime', fcreate_time,
                'updateTime', fupdate_time
            )
        ) AS json_data
        FROM t_invoice_type
        WHERE factive = 1
        ORDER BY finvoice_code
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        result = cursor.fetchone()

        if result and result[0]:
            invoice_types = json.loads(result[0])

            output_data = {
                "meta": {
                    "exportTime": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    "recordCount": len(invoice_types),
                    "scope": "global"
                },
                "invoiceTypes": invoice_types
            }

            output_file = output_dir / "invoice-types.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✓ 发票类型数据导出完成: {len(invoice_types)} 条记录 -> {output_file}")
            return True

    logger.warning("未找到发票类型数据")
    return False


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("基础数据导出开始")
    logger.info("=" * 60)

    try:
        with DatabaseConnection(DB_CONFIG) as conn:
            # 检查 MySQL 版本
            if not check_mysql_version(conn):
                sys.exit(1)

            # 导出全局数据
            logger.info("\n--- 导出全局数据 ---")
            export_global_currencies(conn)
            export_global_invoice_types(conn)

            # 导出代码数据（按国家分组）
            logger.info("\n--- 导出代码数据（按国家分组） ---")
            total_files = 0
            for code_type, code_info in CODE_TYPES.items():
                file_count = export_codes_by_country(conn, code_type, code_info)
                total_files += file_count

            logger.info("\n" + "=" * 60)
            logger.info(f"✓ 导出完成！共生成 {total_files} 个代码文件")
            logger.info(f"输出目录: {OUTPUT_BASE_DIR}")
            logger.info("=" * 60)

    except pymysql.Error as e:
        logger.error(f"数据库错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"导出失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
