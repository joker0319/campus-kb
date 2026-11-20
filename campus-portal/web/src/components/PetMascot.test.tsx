import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PetMascot } from './PetMascot';

describe('墨点助手入口', () => {
  it('是进入助手的链接，文案为知识库的个人助手', () => {
    render(<PetMascot />);
    const entry = screen.getByRole('link', { name: '进入知识库的个人助手' });
    expect(entry.getAttribute('href')).toBe('#/assistant');
    expect(screen.getByText('知识库的个人助手')).toBeTruthy();
  });

  it('不再出现校验台词或问题数字', () => {
    render(<PetMascot />);
    expect(screen.queryByText(/17 处/)).toBeNull();
    expect(screen.queryByText(/换一条校验提示/)).toBeNull();
  });
});
