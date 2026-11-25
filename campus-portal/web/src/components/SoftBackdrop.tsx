import s from '../styles/softBackdrop.module.css';

/** 与首页同源的氛围层：极淡的品牌光晕 + 渐隐网格 + 噪点。
 *  纯装饰、不接收指针事件，放在页面最底层，让内页不再是一整块硬白。 */
export function SoftBackdrop() {
  return (
    <div className={s.bg} aria-hidden="true">
      <div className={s.aurora} />
      <div className={s.grid} />
      <div className={s.noise} />
    </div>
  );
}
