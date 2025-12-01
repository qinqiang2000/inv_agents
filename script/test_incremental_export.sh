#!/bin/bash

# 增量导出功能测试脚本
# 用于验证增量导出功能的正确性和健壮性

# ANSI颜色代码
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 测试配置
EXPORT_SCRIPT="./export_invoice_data.sh"
STATE_FILE="../context/.export_state/.last_export_time"
STATE_DIR="../context/.export_state"
LOCK_FILE="${STATE_DIR}/.export.lock"

# 测试统计
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# 测试结果记录
record_test_result() {
    local test_name="$1"
    local result="$2"

    ((TESTS_TOTAL++))

    if [ "$result" = "PASS" ]; then
        ((TESTS_PASSED++))
        log_success "✓ ${test_name}"
    else
        ((TESTS_FAILED++))
        log_error "✗ ${test_name}"
    fi
}

# 清理测试环境
cleanup() {
    log_info "清理测试环境..."
    rm -f "${STATE_FILE}"
    rm -f "${STATE_FILE}.backup."*
    rm -rf "${LOCK_FILE}"
}

# ========================================
# 测试1: 首次增量运行
# ========================================
test_first_run() {
    log_test "测试1: 首次增量运行(应该导出所有数据)"

    cleanup

    # 执行增量导出(DRY_RUN模式)
    EXPORT_MODE=incremental DRY_RUN=true "${EXPORT_SCRIPT}" > /tmp/test_first_run.log 2>&1
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        # 检查日志中是否包含"首次导出"或"基线时间"
        if grep -q "首次导出\|基线时间\|1970-01-01" /tmp/test_first_run.log; then
            record_test_result "首次增量运行" "PASS"
        else
            log_warning "未找到首次运行的标记"
            record_test_result "首次增量运行" "FAIL"
        fi
    else
        log_error "脚本执行失败，退出码: ${exit_code}"
        record_test_result "首次增量运行" "FAIL"
    fi

    rm -f /tmp/test_first_run.log
}

# ========================================
# 测试2: 状态文件创建和格式验证
# ========================================
test_state_file() {
    log_test "测试2: 状态文件创建和格式验证"

    cleanup

    # 执行增量导出(正式模式，但只导出少量数据)
    EXPORT_MODE=incremental "${EXPORT_SCRIPT}" > /tmp/test_state_file.log 2>&1

    # 检查状态文件是否存在
    if [ -f "${STATE_FILE}" ]; then
        # 验证格式: tenant_id|timestamp|count|status
        if grep -qE '^[0-9]+\|[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\|[0-9]+\|[A-Z]+$' "${STATE_FILE}"; then
            log_success "状态文件格式正确"
            log_info "状态文件内容示例:"
            head -3 "${STATE_FILE}" | sed 's/^/  /'
            record_test_result "状态文件格式" "PASS"
        else
            log_error "状态文件格式不正确"
            record_test_result "状态文件格式" "FAIL"
        fi
    else
        log_error "状态文件未创建"
        record_test_result "状态文件格式" "FAIL"
    fi

    rm -f /tmp/test_state_file.log
}

# ========================================
# 测试3: 无新数据时的行为
# ========================================
test_no_updates() {
    log_test "测试3: 无新数据时的行为(应该导出0条)"

    # 先执行一次增量导出
    EXPORT_MODE=incremental "${EXPORT_SCRIPT}" > /dev/null 2>&1

    # 立即再次执行
    EXPORT_MODE=incremental DRY_RUN=true "${EXPORT_SCRIPT}" > /tmp/test_no_updates.log 2>&1

    # 检查日志中是否包含"无新增数据"或"0 条"
    local no_data_count=$(grep -c "无新增数据\|导出 0 条" /tmp/test_no_updates.log)

    if [ $no_data_count -gt 0 ]; then
        log_success "正确识别无新数据场景"
        record_test_result "无新数据处理" "PASS"
    else
        log_warning "未正确处理无新数据场景"
        record_test_result "无新数据处理" "FAIL"
    fi

    rm -f /tmp/test_no_updates.log
}

# ========================================
# 测试4: DRY_RUN模式验证
# ========================================
test_dry_run() {
    log_test "测试4: DRY_RUN模式(不应写入文件)"

    cleanup

    # 统计导出前的文件数
    local before_count=$(find ../context -name "*.json" 2>/dev/null | wc -l)

    # 执行DRY_RUN
    EXPORT_MODE=incremental DRY_RUN=true "${EXPORT_SCRIPT}" > /tmp/test_dry_run.log 2>&1

    # 统计导出后的文件数
    local after_count=$(find ../context -name "*.json" 2>/dev/null | wc -l)

    # 检查日志中是否包含DRY_RUN标记
    if grep -q "DRY RUN" /tmp/test_dry_run.log; then
        if [ $before_count -eq $after_count ]; then
            log_success "DRY_RUN模式正确，未写入文件"
            record_test_result "DRY_RUN模式" "PASS"
        else
            log_error "DRY_RUN模式异常，文件数发生变化: ${before_count} -> ${after_count}"
            record_test_result "DRY_RUN模式" "FAIL"
        fi
    else
        log_warning "日志中未找到DRY_RUN标记"
        record_test_result "DRY_RUN模式" "FAIL"
    fi

    rm -f /tmp/test_dry_run.log
}

# ========================================
# 测试5: 并发控制
# ========================================
test_concurrent() {
    log_test "测试5: 并发控制(第二个进程应被阻止)"

    cleanup

    # 启动第一个进程(后台运行)
    EXPORT_MODE=incremental "${EXPORT_SCRIPT}" > /tmp/test_concurrent_1.log 2>&1 &
    local pid1=$!

    # 等待第一个进程获取锁
    sleep 2

    # 尝试启动第二个进程
    EXPORT_MODE=incremental "${EXPORT_SCRIPT}" > /tmp/test_concurrent_2.log 2>&1
    local exit_code=$?

    # 检查第二个进程是否被正确阻止
    if [ $exit_code -ne 0 ] && grep -q "另一个导出进程正在运行" /tmp/test_concurrent_2.log; then
        log_success "并发控制正常，第二个进程被阻止"
        record_test_result "并发控制" "PASS"
    else
        log_error "并发控制失败"
        record_test_result "并发控制" "FAIL"
    fi

    # 等待第一个进程完成
    wait $pid1

    rm -f /tmp/test_concurrent_1.log /tmp/test_concurrent_2.log
}

# ========================================
# 测试6: 全量导出模式(向后兼容性)
# ========================================
test_full_export() {
    log_test "测试6: 全量导出模式(向后兼容性)"

    # 执行全量导出(DRY_RUN模式)
    DRY_RUN=true "${EXPORT_SCRIPT}" > /tmp/test_full_export.log 2>&1
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        # 检查日志中是否包含"全量导出"
        if grep -q "全量导出" /tmp/test_full_export.log; then
            log_success "全量导出模式正常工作"
            record_test_result "全量导出模式" "PASS"
        else
            log_warning "未找到全量导出标记"
            record_test_result "全量导出模式" "FAIL"
        fi
    else
        log_error "全量导出失败，退出码: ${exit_code}"
        record_test_result "全量导出模式" "FAIL"
    fi

    rm -f /tmp/test_full_export.log
}

# ========================================
# 测试7: 状态文件备份
# ========================================
test_backup() {
    log_test "测试7: 状态文件自动备份"

    cleanup

    # 创建初始状态文件
    mkdir -p "${STATE_DIR}"
    echo "1|2025-11-28 10:00:00|100|SUCCESS" > "${STATE_FILE}"

    # 执行增量导出(会触发备份)
    EXPORT_MODE=incremental DRY_RUN=true "${EXPORT_SCRIPT}" > /dev/null 2>&1

    # 检查备份文件是否创建
    local backup_count=$(ls -1 "${STATE_FILE}.backup."* 2>/dev/null | wc -l)

    if [ $backup_count -gt 0 ]; then
        log_success "状态文件备份已创建"
        record_test_result "状态文件备份" "PASS"
    else
        log_warning "未找到备份文件"
        record_test_result "状态文件备份" "FAIL"
    fi
}

# ========================================
# 测试8: 脚本语法检查
# ========================================
test_syntax() {
    log_test "测试8: 脚本语法检查"

    bash -n "${EXPORT_SCRIPT}" 2>&1
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log_success "脚本语法正确"
        record_test_result "脚本语法" "PASS"
    else
        log_error "脚本存在语法错误"
        record_test_result "脚本语法" "FAIL"
    fi
}

# ========================================
# 主测试流程
# ========================================
main() {
    echo ""
    log_info "=========================================="
    log_info "增量导出功能测试开始"
    log_info "=========================================="
    echo ""

    # 检查脚本是否存在
    if [ ! -f "${EXPORT_SCRIPT}" ]; then
        log_error "导出脚本不存在: ${EXPORT_SCRIPT}"
        exit 1
    fi

    # 执行所有测试
    test_syntax
    test_first_run
    test_state_file
    test_no_updates
    test_dry_run
    test_concurrent
    test_full_export
    test_backup

    # 清理
    cleanup

    # 输出测试结果
    echo ""
    log_info "=========================================="
    log_info "测试结果汇总"
    log_info "=========================================="
    log_info "总测试数: ${TESTS_TOTAL}"
    log_success "通过: ${TESTS_PASSED}"

    if [ ${TESTS_FAILED} -gt 0 ]; then
        log_error "失败: ${TESTS_FAILED}"
        log_info "=========================================="
        exit 1
    else
        log_info "失败: ${TESTS_FAILED}"
        log_success "=========================================="
        log_success "所有测试通过!"
        log_success "=========================================="
        exit 0
    fi
}

# 执行主流程
main
