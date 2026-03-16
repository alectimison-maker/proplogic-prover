/**
 * 用户行为追踪 - 非阻塞埋点
 * 使用 navigator.sendBeacon 确保不阻塞主线程
 */

/**
 * 发送埋点事件
 * @param {string} type - 事件类型
 * @param {string} [detail=''] - 事件详情
 */
function track(type, detail = '') {
  try {
    const payload = JSON.stringify({
      event_type: type,
      page: location.pathname,
      detail: detail,
    });
    // sendBeacon 失败时降级到 fetch (fire-and-forget)
    const ok = navigator.sendBeacon('/api/track', new Blob([payload], { type: 'application/json' }));
    if (!ok) {
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    }
  } catch (e) {
    // 埋点静默失败，不影响主功能
  }
}

// 页面加载时自动触发 page_view
document.addEventListener('DOMContentLoaded', () => {
  track('page_view');
});
