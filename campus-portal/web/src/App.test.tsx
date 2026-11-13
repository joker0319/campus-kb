import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import App from './App';

const list = () => screen.getAllByRole('listitem');
const evidence = () => screen.getByLabelText('判定依据');
const chip = (name: RegExp) => screen.getByRole('tab', { name });

describe('校稿台', () => {
  beforeEach(() => {
    // 首页是默认路由，校稿台用例统一先切到 #/desk
    window.location.hash = '#/desk';
  });
  afterEach(() => {
    window.location.hash = '';
  });

  it('渲染 17 条命中，与引擎输出一致', () => {
    render(<App />);
    expect(list()).toHaveLength(17);
  });

  it('默认选中 NAME-001，依据栏给出规则名、原文与出处', () => {
    render(<App />);
    const pane = evidence();
    expect(within(pane).getByText('校名首次出现用全称')).toBeTruthy();
    expect(within(pane).getByText(/全称：香港城市大学（东莞）/)).toBeTruthy();
    expect(within(pane).getByText(/一、学校定位与基本信息/)).toBeTruthy();
  });

  it('点选问题后依据栏切换到对应规则', () => {
    render(<App />);
    const item = screen
      .getByText('出现「中、港、台」并列提法，违反领土主权类表述规范')
      .closest('[role="listitem"]');
    expect(item).not.toBeNull();
    fireEvent.click(within(item as HTMLElement).getByRole('button', { pressed: false }));

    const pane = evidence();
    expect(within(pane).getByText('SOEV-002')).toBeTruthy();
    expect(within(pane).getByText(/海峡两岸暨香港/)).toBeTruthy();
  });

  it('按级别筛选：错误 11 条 / 警告 6 条', () => {
    render(<App />);
    fireEvent.click(chip(/错误/));
    expect(list()).toHaveLength(11);

    fireEvent.click(chip(/警告/));
    expect(list()).toHaveLength(6);
  });

  it('忽略一条后从清单移除，计数同步', () => {
    render(<App />);
    const first = list()[0] as HTMLElement;
    fireEvent.click(within(first).getByTitle('忽略这条'));

    expect(list()).toHaveLength(16);
    expect(within(chip(/全部/)).getByText('16')).toBeTruthy();
  });

  it('关掉「显示标记」后正文进入纯净阅读态', () => {
    const { container } = render(<App />);
    const prose = container.querySelector('[class*="prose"]') as HTMLElement;
    expect(prose.className).not.toContain('plain');

    fireEvent.click(screen.getByLabelText('显示标记'));
    expect(prose.className).toContain('plain');
  });

  it('键盘 j 逐条向下、k 回退', () => {
    render(<App />);
    // 初始 NAME-001@3，下一条是同行的 PUNCT-001@3
    fireEvent.keyDown(window, { key: 'j' });
    expect(within(evidence()).getByText('中文语境用全角标点')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'k' });
    expect(within(evidence()).getByText('校名首次出现用全称')).toBeTruthy();
  });
});
