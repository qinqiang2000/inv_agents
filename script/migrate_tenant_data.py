#!/usr/bin/env python3
"""
租户数据迁移脚本
将现有数据从旧目录结构迁移到新的租户隔离目录结构

旧结构:
  context/invoices/{tenant_id}/{country}/
  context/pending-invoices/{tenant_id}/

新结构:
  tenant-data/{tenant_id}/invoices/{country}/
  tenant-data/{tenant_id}/pending-invoices/
"""

import os
import shutil
import logging
import argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 路径配置
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONTEXT_DIR = PROJECT_ROOT / "context"
TENANT_DATA_DIR = PROJECT_ROOT / "tenant-data"

# 需要清理的旧目录（context 根目录下的数字目录，是更旧的发票目录）
OLD_TENANT_DIRS_IN_CONTEXT = ["1", "10", "89", "91", "92"]


def migrate_invoices(dry_run: bool = False) -> int:
    """
    迁移历史发票数据

    Returns:
        迁移的租户数量
    """
    logger.info("=== 开始迁移历史发票数据 ===")

    old_invoices_dir = CONTEXT_DIR / "invoices"

    if not old_invoices_dir.exists():
        logger.warning(f"旧发票目录不存在: {old_invoices_dir}")
        return 0

    migrated_count = 0

    for tenant_dir in sorted(old_invoices_dir.iterdir()):
        if not tenant_dir.is_dir():
            continue

        # 跳过隐藏目录（如 .export_state）
        if tenant_dir.name.startswith('.'):
            continue

        tenant_id = tenant_dir.name
        new_tenant_invoices = TENANT_DATA_DIR / tenant_id / "invoices"

        # 统计文件数
        file_count = sum(1 for _ in tenant_dir.rglob("*.json"))
        logger.info(f"迁移租户 {tenant_id} 的发票数据 ({file_count} 个文件)...")

        if dry_run:
            logger.info(f"  [DRY RUN] {tenant_dir} -> {new_tenant_invoices}")
            migrated_count += 1
            continue

        # 创建目标目录
        new_tenant_invoices.parent.mkdir(parents=True, exist_ok=True)

        if new_tenant_invoices.exists():
            logger.warning(f"  目标目录已存在，跳过: {new_tenant_invoices}")
            continue

        # 移动目录
        shutil.move(str(tenant_dir), str(new_tenant_invoices))
        logger.info(f"  {tenant_dir} -> {new_tenant_invoices}")
        migrated_count += 1

    return migrated_count


def migrate_pending_invoices(dry_run: bool = False) -> int:
    """
    迁移待处理发票数据

    Returns:
        迁移的租户数量
    """
    logger.info("=== 开始迁移待处理发票数据 ===")

    old_pending_dir = CONTEXT_DIR / "pending-invoices"

    if not old_pending_dir.exists():
        logger.warning(f"旧待处理发票目录不存在: {old_pending_dir}")
        return 0

    migrated_count = 0

    for tenant_dir in sorted(old_pending_dir.iterdir()):
        if not tenant_dir.is_dir():
            continue

        tenant_id = tenant_dir.name
        new_tenant_pending = TENANT_DATA_DIR / tenant_id / "pending-invoices"

        # 统计文件数
        file_count = len(list(tenant_dir.iterdir()))
        logger.info(f"迁移租户/应用 {tenant_id} 的待处理发票 ({file_count} 个文件)...")

        if dry_run:
            logger.info(f"  [DRY RUN] {tenant_dir} -> {new_tenant_pending}")
            migrated_count += 1
            continue

        # 创建目标目录
        new_tenant_pending.parent.mkdir(parents=True, exist_ok=True)

        if new_tenant_pending.exists():
            logger.warning(f"  目标目录已存在，跳过: {new_tenant_pending}")
            continue

        # 移动目录
        shutil.move(str(tenant_dir), str(new_tenant_pending))
        logger.info(f"  {tenant_dir} -> {new_tenant_pending}")
        migrated_count += 1

    return migrated_count


def migrate_export_state(dry_run: bool = False) -> bool:
    """
    迁移导出状态文件

    Returns:
        是否迁移成功
    """
    logger.info("=== 开始迁移导出状态文件 ===")

    old_state_dir = CONTEXT_DIR / "invoices" / ".export_state"
    new_state_dir = TENANT_DATA_DIR / ".export_state"

    if not old_state_dir.exists():
        # 尝试查找 context/.export_state
        old_state_dir = CONTEXT_DIR / ".export_state"

    if not old_state_dir.exists():
        logger.info("未找到导出状态目录，跳过迁移")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] {old_state_dir} -> {new_state_dir}")
        return True

    new_state_dir.parent.mkdir(parents=True, exist_ok=True)

    if new_state_dir.exists():
        logger.warning(f"目标状态目录已存在，跳过: {new_state_dir}")
        return False

    shutil.move(str(old_state_dir), str(new_state_dir))
    logger.info(f"  {old_state_dir} -> {new_state_dir}")
    return True


def cleanup_old_directories(dry_run: bool = False):
    """清理旧的租户目录（在 context 根目录下的数字目录）"""
    logger.info("=== 清理旧的租户目录 ===")

    for old_dir_name in OLD_TENANT_DIRS_IN_CONTEXT:
        old_dir = CONTEXT_DIR / old_dir_name
        if old_dir.exists():
            if dry_run:
                logger.info(f"[DRY RUN] 将删除旧目录: {old_dir}")
            else:
                logger.info(f"删除旧目录: {old_dir}")
                shutil.rmtree(old_dir)


def cleanup_empty_directories(dry_run: bool = False):
    """清理空的旧目录"""
    logger.info("=== 清理空目录 ===")

    dirs_to_check = [
        CONTEXT_DIR / "invoices",
        CONTEXT_DIR / "pending-invoices"
    ]

    for dir_path in dirs_to_check:
        if not dir_path.exists():
            continue

        remaining = list(dir_path.iterdir())
        # 只剩下隐藏文件（如 .DS_Store）或 .export_state 时也删除
        remaining_non_hidden = [f for f in remaining if not f.name.startswith('.')]

        if not remaining_non_hidden:
            if dry_run:
                logger.info(f"[DRY RUN] 将删除空目录: {dir_path}")
            else:
                logger.info(f"删除空目录: {dir_path}")
                shutil.rmtree(dir_path)


def verify_migration():
    """验证迁移结果"""
    logger.info("=== 验证迁移结果 ===")

    # 检查新目录结构
    if TENANT_DATA_DIR.exists():
        total_invoices = 0
        total_pending = 0

        for tenant_dir in sorted(TENANT_DATA_DIR.iterdir()):
            if not tenant_dir.is_dir() or tenant_dir.name.startswith('.'):
                continue

            tenant_id = tenant_dir.name
            invoices_dir = tenant_dir / "invoices"
            pending_dir = tenant_dir / "pending-invoices"

            invoice_count = 0
            if invoices_dir.exists():
                for country_dir in invoices_dir.iterdir():
                    if country_dir.is_dir():
                        invoice_count += len(list(country_dir.glob("*.json")))

            pending_count = 0
            if pending_dir.exists():
                pending_count = len([f for f in pending_dir.iterdir() if f.is_file()])

            logger.info(f"  租户 {tenant_id}: {invoice_count} 个历史发票, {pending_count} 个待处理发票")
            total_invoices += invoice_count
            total_pending += pending_count

        logger.info(f"总计: {total_invoices} 个历史发票, {total_pending} 个待处理发票")
    else:
        logger.warning(f"租户数据目录不存在: {TENANT_DATA_DIR}")

    # 检查公共数据
    basic_data_dir = CONTEXT_DIR / "basic-data"
    if basic_data_dir.exists():
        global_dir = basic_data_dir / "global"
        codes_dir = basic_data_dir / "codes"

        global_files = list(global_dir.glob("*.json")) if global_dir.exists() else []
        codes_dirs = list(codes_dir.iterdir()) if codes_dir.exists() else []

        logger.info(f"公共数据: {len(global_files)} 个全局文件, {len(codes_dirs)} 个代码目录")
    else:
        logger.warning(f"公共数据目录不存在: {basic_data_dir}")


def main(dry_run: bool = False):
    """主函数"""
    logger.info("=" * 60)
    logger.info("租户数据迁移脚本")
    logger.info("=" * 60)
    logger.info(f"源目录: {CONTEXT_DIR}")
    logger.info(f"目标目录: {TENANT_DATA_DIR}")

    if dry_run:
        logger.info("[DRY RUN] 仅预览，不执行实际迁移")

    logger.info("")

    # 创建新的租户数据根目录
    if not dry_run:
        TENANT_DATA_DIR.mkdir(exist_ok=True)

    # 执行迁移
    invoices_migrated = migrate_invoices(dry_run)
    pending_migrated = migrate_pending_invoices(dry_run)
    state_migrated = migrate_export_state(dry_run)
    cleanup_old_directories(dry_run)
    cleanup_empty_directories(dry_run)

    # 验证
    if not dry_run:
        verify_migration()

    logger.info("")
    logger.info("=" * 60)
    if dry_run:
        logger.info("[DRY RUN] 预览完成!")
    else:
        logger.info("迁移完成!")
    logger.info(f"  历史发票: 迁移了 {invoices_migrated} 个租户")
    logger.info(f"  待处理发票: 迁移了 {pending_migrated} 个租户/应用")
    logger.info(f"  导出状态: {'已迁移' if state_migrated else '跳过'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='租户数据迁移脚本')
    parser.add_argument('--dry-run', '-d', action='store_true', help='试运行模式，仅预览不执行')
    args = parser.parse_args()

    main(dry_run=args.dry_run)
