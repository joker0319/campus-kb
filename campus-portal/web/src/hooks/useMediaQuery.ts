import { useCallback, useSyncExternalStore } from 'react';

/**
 * 断点与 CSS 媒体查询保持一致，避免「样式变了但逻辑没变」。
 *
 * 用 useSyncExternalStore 而不是 useEffect + setState：媒体查询是外部数据源，
 * 这样首帧就能读到正确值，不会先渲染一次错的布局再纠正（视觉上表现为闪一下）。
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener('change', onStoreChange);
      return () => mql.removeEventListener('change', onStoreChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);

  // 服务端渲染/预渲染时没有窗口，按桌面断点处理
  const getServerSnapshot = () => false;

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
