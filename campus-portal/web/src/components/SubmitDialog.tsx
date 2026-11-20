import { useEffect, useRef, useState } from 'react';
import { DRAFT_TEXT } from '../data/content';
import s from '../styles/dialog.module.css';

interface Props {
  onClose: () => void;
  onSubmit: (text: string) => void;
}

/** 粘贴稿件弹窗：提交任意正文给 /api/review，替换当前送审稿 */
export function SubmitDialog({ onClose, onSubmit }: Props) {
  const [text, setText] = useState('');
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    areaRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const trimmed = text.trim();

  return (
    <div className={s.overlay} role="presentation" onMouseDown={onClose}>
      <div
        className={s.panel}
        role="dialog"
        aria-modal="true"
        aria-label="粘贴稿件"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className={s.head}>
          <div>
            <b>粘贴稿件</b>
            <p>正文按行送检，命中处会直接标红并可点回依据</p>
          </div>
          <button type="button" className={s.close} onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </div>

        <textarea
          ref={areaRef}
          className={s.area}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'【媒体传讯处】标题\n通知动态\n正文……'}
          aria-label="稿件正文"
        />

        <div className={s.foot}>
          <span className={s.meta}>
            {trimmed.length} 字 · {trimmed ? trimmed.split('\n').length : 0} 行
          </span>
          <button type="button" className={s.ghost} onClick={() => setText(DRAFT_TEXT)}>
            填入示例
          </button>
          <button
            type="button"
            className={s.primary}
            disabled={!trimmed}
            onClick={() => onSubmit(trimmed)}
          >
            校验这篇
          </button>
        </div>
      </div>
    </div>
  );
}
