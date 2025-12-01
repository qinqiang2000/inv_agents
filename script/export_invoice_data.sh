#!/bin/bash

# 发票数据导出脚本
# 从t_invoice表中读取开票成功(fissue_status=3)的数据，按租户和国家组织存储
# 支持全量导出和增量导出两种模式

# 数据库配置
DB_HOST="jump-test.piaozone.com"
DB_PORT="3306"
DB_USER="rnd"
DB_PASSWORD="ZaFOjoFp&SdB8bum"
DB_NAME="test_jin"

# 输出目录配置 - 上级目录的context目录
OUTPUT_BASE_DIR="../context"

# 运行模式配置
EXPORT_MODE="${EXPORT_MODE:-full}"           # full: 全量导出(默认), incremental: 增量导出
DRY_RUN="${DRY_RUN:-false}"                  # true: 测试模式(不写入文件), false: 正常模式
STATE_FILE_DIR="${OUTPUT_BASE_DIR}/.export_state"
STATE_FILE="${STATE_FILE_DIR}/.last_export_time"
LOCK_FILE="${STATE_FILE_DIR}/.export.lock"
TIME_BUFFER_SECONDS=300                       # 5分钟安全边界，避免捕获正在进行的事务

# ANSI颜色代码
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# ========================================
# 状态管理函数
# ========================================

# 初始化状态文件和目录
init_state_file() {
    if [ "${EXPORT_MODE}" != "incremental" ]; then
        return 0
    fi

    mkdir -p "${STATE_FILE_DIR}"

    if [ ! -f "${STATE_FILE}" ]; then
        log_info "创建状态文件: ${STATE_FILE}"
        touch "${STATE_FILE}"
    fi

    # 验证状态文件格式
    if [ -s "${STATE_FILE}" ]; then
        if ! grep -qE '^[0-9]+\|[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\|[0-9]+\|[A-Z]+$' "${STATE_FILE}"; then
            log_warning "状态文件格式不正确，将备份后重新创建"
            mv "${STATE_FILE}" "${STATE_FILE}.backup.$(date +%Y%m%d%H%M%S)"
            touch "${STATE_FILE}"
        fi
    fi
}

# 获取租户的上次导出时间
# 参数: tenant_id
# 返回: 时间戳字符串，如果不存在则返回空
get_last_export_time() {
    local tenant_id="$1"

    if [ ! -f "${STATE_FILE}" ]; then
        echo ""
        return
    fi

    local last_time=$(grep "^${tenant_id}|" "${STATE_FILE}" | cut -d'|' -f2)
    echo "${last_time}"
}

# 更新租户的导出时间(兼容macOS和Linux)
# 参数: tenant_id, export_time, record_count, status
update_export_time() {
    local tenant_id="$1"
    local export_time="$2"
    local record_count="$3"
    local status="${4:-SUCCESS}"

    if [ "${DRY_RUN}" = "true" ]; then
        log_info "[DRY RUN] 将更新状态: 租户${tenant_id} -> ${export_time} (${record_count}条)"
        return 0
    fi

    local temp_file="${STATE_FILE}.tmp.$$"

    # 移除旧记录并添加新记录
    if [ -f "${STATE_FILE}" ]; then
        grep -v "^${tenant_id}|" "${STATE_FILE}" > "${temp_file}" || true
    fi

    echo "${tenant_id}|${export_time}|${record_count}|${status}" >> "${temp_file}"

    # 原子替换（使用mv的原子性）
    mv "${temp_file}" "${STATE_FILE}"
}

# 计算导出安全边界时间(当前时间 - 5分钟)
calculate_export_boundary() {
    if command -v gdate &> /dev/null; then
        # macOS with GNU coreutils
        gdate -d "${TIME_BUFFER_SECONDS} seconds ago" '+%Y-%m-%d %H:%M:%S'
    else
        # Linux
        date -d "${TIME_BUFFER_SECONDS} seconds ago" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || \
        date -v-${TIME_BUFFER_SECONDS}S '+%Y-%m-%d %H:%M:%S'
    fi
}

# ========================================
# 并发控制函数
# ========================================

# 获取导出锁
acquire_lock() {
    if [ "${EXPORT_MODE}" != "incremental" ]; then
        return 0
    fi

    mkdir -p "${STATE_FILE_DIR}"

    if ! mkdir "${LOCK_FILE}" 2>/dev/null; then
        log_error "另一个导出进程正在运行(锁文件: ${LOCK_FILE})"
        log_error "如果确认没有其他进程，请手动删除锁目录: rm -rf ${LOCK_FILE}"
        exit 1
    fi

    log_info "已获取导出锁"
}

# 释放导出锁
release_lock() {
    if [ "${EXPORT_MODE}" = "incremental" ] && [ -d "${LOCK_FILE}" ]; then
        rm -rf "${LOCK_FILE}"
        log_info "已释放导出锁"
    fi
}

# ========================================
# 错误处理函数
# ========================================

# 检查磁盘空间(至少需要100MB)
check_disk_space() {
    local available

    if command -v df &> /dev/null; then
        available=$(df -m "${OUTPUT_BASE_DIR}" 2>/dev/null | awk 'NR==2 {print $4}')

        if [ -n "${available}" ] && [ "${available}" -lt 100 ]; then
            log_error "磁盘空间不足: ${available}MB (需要至少100MB)"
            return 1
        fi
    fi

    return 0
}

# 备份状态文件
backup_state_file() {
    if [ -f "${STATE_FILE}" ] && [ -s "${STATE_FILE}" ]; then
        cp "${STATE_FILE}" "${STATE_FILE}.backup.$(date +%Y%m%d%H%M%S)"
    fi
}

# 检查mysql命令是否存在
check_mysql_command() {
    if ! command -v mysql &> /dev/null; then
        log_error "mysql命令未找到，请先安装MySQL客户端"
        exit 1
    fi
}

# ========================================
# 查询构建函数
# ========================================

# 构建查询SQL
# 参数: mode, tenant_id, last_time, boundary_time
build_query() {
    local mode="$1"
    local tenant_id="$2"
    local last_time="$3"
    local boundary_time="$4"

    # 基础查询
    local base_query="SELECT
    ftenant_id,
    fcountry,
    DATE_FORMAT(fissue_date, '%Y%m%d') AS fissue_date_formatted,
    finvoice_no,
    fext_field,
    fupdate_time
FROM t_invoice
WHERE fissue_status = 3
  AND fext_field IS NOT NULL
  AND fext_field != ''
  AND finvoice_no IS NOT NULL
  AND finvoice_no != ''
  AND fissue_date IS NOT NULL"

    if [ "${mode}" = "incremental" ]; then
        # 增量模式: 添加租户和时间过滤
        echo "${base_query}
  AND ftenant_id = '${tenant_id}'
  AND fupdate_time > '${last_time}'
  AND fupdate_time <= '${boundary_time}'
ORDER BY fupdate_time ASC, finvoice_no ASC"
    else
        # 全量模式: 保持原有排序
        echo "${base_query}
ORDER BY ftenant_id, fcountry, fissue_date, finvoice_no"
    fi
}

# ========================================
# 数据处理函数
# ========================================

# 处理单条发票记录
# 参数: tenant_id, country, issue_date, invoice_no, ext_field
process_invoice_record() {
    local tenant_id="$1"
    local country="$2"
    local issue_date="$3"
    local invoice_no="$4"
    local ext_field="$5"

    # 处理国家字段为NULL的情况
    if [ "$country" = "NULL" ] || [ -z "$country" ]; then
        country="UNKNOWN"
        log_warning "发票号 ${invoice_no} 的国家字段为空，使用默认值: UNKNOWN"
    fi

    # 创建租户和国家目录
    local tenant_dir="${OUTPUT_BASE_DIR}/${tenant_id}"
    local country_dir="${tenant_dir}/${country}"
    mkdir -p "${country_dir}"

    # 生成文件名: fissue_date+finvoice_no.json
    # 替换发票号中的特殊字符为下划线
    local safe_invoice_no=$(echo "${invoice_no}" | sed 's/[\/\\:*?"<>|]/_/g')
    local file_name="${issue_date}+${safe_invoice_no}.json"
    local file_path="${country_dir}/${file_name}"

    # 写入JSON文件(除非是DRY_RUN模式)
    if [ "${DRY_RUN}" = "true" ]; then
        return 0
    fi

    if echo "${ext_field}" > "${file_path}"; then
        return 0
    else
        log_error "写入文件失败: ${file_path}"
        return 1
    fi
}

# ========================================
# 导出函数
# ========================================

# 全量导出函数(保持原有逻辑)
export_full() {
    log_info "=========================================="
    log_info "执行全量导出"
    log_info "=========================================="

    local query=$(build_query "full")

    local export_count=0
    local error_count=0
    local tenant_count=0
    local current_tenant=""

    mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" \
        --batch --skip-column-names -e "${query}" | \
    while IFS=$'\t' read -r tenant_id country issue_date invoice_no ext_field update_time; do
        # 跳过空行
        if [ -z "$tenant_id" ]; then
            continue
        fi

        # 统计租户数量
        if [ "$tenant_id" != "$current_tenant" ]; then
            if [ -n "$current_tenant" ]; then
                log_success "租户 ${current_tenant} 处理完成"
            fi
            current_tenant="$tenant_id"
            ((tenant_count++))
            log_info "开始处理租户: ${tenant_id}"
        fi

        # 处理记录
        if process_invoice_record "${tenant_id}" "${country}" "${issue_date}" "${invoice_no}" "${ext_field}"; then
            ((export_count++))
            if [ $((export_count % 100)) -eq 0 ]; then
                log_info "已导出 ${export_count} 条记录..."
            fi
        else
            ((error_count++))
        fi
    done

    # 检查查询是否成功
    local query_status=$?
    if [ ${query_status} -ne 0 ]; then
        log_error "数据库查询失败，请检查数据库连接配置"
        return 1
    fi

    # 输出统计信息
    echo ""
    log_success "=========================================="
    log_success "全量导出完成!"
    log_success "=========================================="
    log_info "租户数量: ${tenant_count}"
    log_info "成功导出: ${export_count} 条记录"
    if [ ${error_count} -gt 0 ]; then
        log_warning "失败数量: ${error_count} 条记录"
    fi
    log_info "输出目录: ${OUTPUT_BASE_DIR}"
    log_success "=========================================="

    return 0
}

# 增量导出函数
export_incremental() {
    log_info "=========================================="
    log_info "执行增量导出"
    log_info "=========================================="

    # 计算安全边界时间
    local export_boundary=$(calculate_export_boundary)
    if [ -z "${export_boundary}" ]; then
        log_error "计算导出边界时间失败"
        return 1
    fi

    log_info "导出时间边界: ${export_boundary}"

    # 获取所有租户列表
    log_info "获取租户列表..."
    local tenants=$(mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" \
        --batch --skip-column-names -e "SELECT DISTINCT ftenant_id FROM t_invoice WHERE fissue_status = 3 ORDER BY ftenant_id")

    if [ $? -ne 0 ] || [ -z "${tenants}" ]; then
        log_error "获取租户列表失败"
        return 1
    fi

    local total_export_count=0
    local total_tenant_count=0

    # 逐租户处理
    for tenant_id in ${tenants}; do
        # 跳过空值和特殊租户
        if [ -z "${tenant_id}" ] || [ "${tenant_id}" = "NULL" ]; then
            continue
        fi

        ((total_tenant_count++))

        # 获取上次导出时间
        local last_time=$(get_last_export_time "${tenant_id}")
        if [ -z "${last_time}" ]; then
            last_time="1970-01-01 00:00:00"
            log_info "租户 ${tenant_id}: 首次导出，基线时间: ${last_time}"
        fi

        log_info "租户 ${tenant_id}: ${last_time} -> ${export_boundary}"

        # 构建并执行查询
        local query=$(build_query "incremental" "${tenant_id}" "${last_time}" "${export_boundary}")

        local tenant_export_count=0
        local tenant_error_count=0

        mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" \
            --batch --skip-column-names -e "${query}" | \
        while IFS=$'\t' read -r tid country issue_date invoice_no ext_field update_time; do
            # 跳过空行
            if [ -z "$tid" ]; then
                continue
            fi

            # 处理记录
            if process_invoice_record "${tid}" "${country}" "${issue_date}" "${invoice_no}" "${ext_field}"; then
                ((tenant_export_count++))
            else
                ((tenant_error_count++))
            fi
        done

        # 检查查询状态
        if [ $? -ne 0 ]; then
            log_error "租户 ${tenant_id}: 查询失败"
            update_export_time "${tenant_id}" "${export_boundary}" "0" "FAILED"
            continue
        fi

        # 更新状态(即使记录数为0也要更新，表示已同步到边界时间)
        update_export_time "${tenant_id}" "${export_boundary}" "${tenant_export_count}" "SUCCESS"

        if [ ${tenant_export_count} -gt 0 ]; then
            log_success "租户 ${tenant_id}: 导出 ${tenant_export_count} 条新记录"
        else
            log_info "租户 ${tenant_id}: 无新增数据"
        fi

        ((total_export_count += tenant_export_count))
    done

    # 输出统计信息
    echo ""
    log_success "=========================================="
    log_success "增量导出完成!"
    log_success "=========================================="
    log_info "处理租户数: ${total_tenant_count}"
    log_info "成功导出: ${total_export_count} 条新记录"
    log_info "输出目录: ${OUTPUT_BASE_DIR}"
    log_info "状态文件: ${STATE_FILE}"
    log_success "=========================================="

    return 0
}

# ========================================
# 主流程
# ========================================

main() {
    # 预检查
    check_mysql_command
    check_disk_space || exit 1

    # 获取并发锁
    acquire_lock
    trap release_lock EXIT INT TERM

    # 初始化
    mkdir -p "${OUTPUT_BASE_DIR}"
    init_state_file

    # 备份状态文件
    if [ "${EXPORT_MODE}" = "incremental" ]; then
        backup_state_file
    fi

    # 日志模式信息
    if [ "${DRY_RUN}" = "true" ]; then
        log_warning "=========================================="
        log_warning "DRY RUN 模式: 不会实际写入文件"
        log_warning "=========================================="
    fi

    log_info "运行模式: ${EXPORT_MODE}"

    # 根据模式执行
    if [ "${EXPORT_MODE}" = "incremental" ]; then
        export_incremental
    else
        export_full
    fi

    local exit_code=$?

    # 显示目录结构示例(仅全量导出)
    if [ "${EXPORT_MODE}" = "full" ] && [ ${exit_code} -eq 0 ]; then
        echo ""
        log_info "目录结构示例:"
        tree -L 3 -d "${OUTPUT_BASE_DIR}" 2>/dev/null || find "${OUTPUT_BASE_DIR}" -type d -maxdepth 3 | head -10
    fi

    exit ${exit_code}
}

# 执行主流程
main
