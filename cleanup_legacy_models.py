#!/usr/bin/env python3
"""清理旧版本地翻译方案（MarianMT / opus-mt）的遗留缓存。

2026-09 重构为 LLM-only 翻译后（commit 9f6f115 "Switch to LLM-only translation"），
以下内容不再被本项目使用，可安全回收：

  1. HuggingFace 缓存中的 opus-mt 模型权重（300MB ~ 1.3GB / 个）
  2. 本项目 venv 里的 torch / transformers / sentencepiece / sacremoses（约 1.3GB）

防误删设计：
  - 默认 dry-run：只列出将要删除的内容，加 --yes 才真正执行
  - HuggingFace 缓存只删名字精确匹配 opus-mt 英译中模型的目录，
    同缓存里的其他模型（包括其他 opus-mt 方向）一律不动，只提示
  - 只卸载「位于本项目目录内」的 venv 中的包；系统 Python、其他项目的
    venv 一律不碰
  - 若 pyproject.toml 仍声明这些依赖（说明尚未升级到 LLM 方案），自动中止
  - 不清理 uv / pip 的下载缓存：它们跨项目共享，其他项目的 torch 轮子
    还在用；清了只会让别的项目重新下载 1GB+

用法：
  python cleanup_legacy_models.py          # dry-run，先看会删什么
  python cleanup_legacy_models.py --yes    # 实际执行
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 历史上本项目用过的 opus-mt 模型（英译中）
LEGACY_HF_MODELS = [
    'models--Helsinki-NLP--opus-mt-en-zh',
    'models--Helsinki-NLP--opus-mt-tc-big-en-zh',
]
# 旧 pyproject.toml 声明过的本地翻译依赖
LEGACY_PACKAGES = ['torch', 'transformers', 'sentencepiece', 'sacremoses']

PROJECT_ROOT = Path(__file__).resolve().parent


def human(n: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.2f} {unit}' if unit != 'B' else f'{int(n)} B'
        n /= 1024
    return f'{n:.2f} TB'


def dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob('*'):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


# ---------------------------------------------------------------------------
# 1) HuggingFace 模型缓存
# ---------------------------------------------------------------------------

def hf_cache_roots() -> list:
    """返回所有可能的 HF 缓存目录（去重），兼容自定义 HF_HOME 等环境变量。"""
    home = Path.home()
    roots = []

    hf_home = os.environ.get('HF_HOME')
    if hf_home:
        roots.append(Path(hf_home) / 'hub')

    for var in ('HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE'):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]))

    # transformers 老版本（<4.22）的缓存布局
    legacy_dir = os.environ.get('TRANSFORMERS_CACHE') or os.environ.get('HF_TRANSFORMERS_CACHE')
    if legacy_dir:
        roots.append(Path(legacy_dir))
    roots.append(home / '.cache' / 'huggingface' / 'transformers')

    # 默认 hub 布局
    roots.append(home / '.cache' / 'huggingface' / 'hub')

    seen, unique = set(), []
    for r in roots:
        r = Path(r)
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def plan_hf_cleanup(execute: bool) -> int:
    print('\n== HuggingFace 模型缓存 ==')
    freed = 0
    found_any = False

    for cache in hf_cache_roots():
        if not cache.is_dir():
            continue
        print(f'缓存目录: {cache}')

        # 精确匹配本项目用过的模型
        for name in LEGACY_HF_MODELS:
            target = cache / name
            lock_dir = cache.parent / '.locks' / name
            if target.exists():
                found_any = True
                size = dir_size(target)
                print(f'  [删] {name}  ({human(size)})')
                if execute:
                    shutil.rmtree(target, ignore_errors=True)
                if lock_dir.exists():
                    print(f'  [删] 对应锁目录 {lock_dir.relative_to(cache.parent)}')
                    if execute:
                        shutil.rmtree(lock_dir, ignore_errors=True)
                freed += size

        # 老版 transformers 缓存布局：目录名形如 opus-mt-xxx 的子目录
        if cache.name == 'transformers':
            for child in sorted(cache.glob('*opus-mt*')):
                if child.is_dir():
                    found_any = True
                    size = dir_size(child)
                    print(f'  [删] {child.name}  ({human(size)})')
                    if execute:
                        shutil.rmtree(child, ignore_errors=True)
                    freed += size

        # 其他 opus-mt 模型（非英译中方向）：只提示，不自动删
        for child in sorted(cache.glob('models--Helsinki-NLP--opus-mt-*')):
            if child.name not in LEGACY_HF_MODELS:
                print(f'  [提示] 发现其他 opus-mt 模型，本项目未用过，未删除: {child.name} '
                      f'({human(dir_size(child))})')

    if not found_any:
        print('  未发现 opus-mt 模型缓存（可能已清理，或当时在 Docker 内运行）')
    return freed


# ---------------------------------------------------------------------------
# 2) 项目 venv 里的旧依赖
# ---------------------------------------------------------------------------

def pyproject_still_declares_legacy() -> bool:
    """pyproject.toml 是否仍声明旧依赖（声明了说明还没升级到 LLM 方案，不能卸）。"""
    pyproject = PROJECT_ROOT / 'pyproject.toml'
    if not pyproject.exists():
        return False
    try:
        text = pyproject.read_text(encoding='utf-8')
    except Exception:
        return False
    still = [p for p in LEGACY_PACKAGES if re.search(rf'["\']{p}[=<>~"\']', text)]
    return bool(still)


def locate_venv() -> tuple:
    """定位本项目自己的 venv，返回 (venv_path, python_exe)。找不到返回 (None, None)。

    只接受位于项目根目录内的 venv，VIRTUAL_ENV 指向别处时忽略（防误删）。
    """
    candidates = [PROJECT_ROOT / '.venv']
    env_venv = os.environ.get('VIRTUAL_ENV')
    if env_venv:
        p = Path(env_venv)
        # 必须在项目根内，才认定是本项目的 venv
        if PROJECT_ROOT in p.resolve().parents or p.resolve() == PROJECT_ROOT:
            candidates.insert(0, p)

    for venv in candidates:
        if (venv / 'pyvenv.cfg').exists():
            py = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            if py.exists():
                return venv, py
    return None, None


def installed_packages(venv_python: Path) -> set:
    """用 venv 自己的解释器查询已安装包名（不污染当前进程）。"""
    code = (
        "import importlib.metadata as m;"
        "print('\\n'.join(d.metadata['Name'].lower() for d in m.distributions()))"
    )
    try:
        r = subprocess.run([str(venv_python), '-c', code],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return set(r.stdout.lower().split())
    except Exception:
        pass
    return set()


def plan_venv_cleanup(execute: bool) -> int:
    print('\n== 项目 venv 旧依赖 ==')
    if pyproject_still_declares_legacy():
        print('  [中止] pyproject.toml 仍声明 torch/transformers 等依赖，'
              '尚未升级到 LLM 方案，不卸载。')
        return 0

    venv, venv_python = locate_venv()
    if not venv:
        print('  未找到本项目 .venv（跳过。venv 不存在或不在项目目录内，不做任何操作）')
        return 0
    print(f'venv: {venv}')

    installed = installed_packages(venv_python)
    to_remove = [p for p in LEGACY_PACKAGES if p in installed]
    if not to_remove:
        print('  venv 中没有旧依赖（可能已清理）')
        return 0

    # 预估可回收大小
    site = next(iter(venv.glob('Lib/site-packages'))) if os.name == 'nt' \
        else next(iter(venv.glob('lib/python*/site-packages')), None)
    est = 0
    if site:
        for p in to_remove:
            for d in site.glob(f'{p}*'):
                if d.is_dir():
                    est += dir_size(d)

    print(f'  [卸载] {", ".join(to_remove)}  (约 {human(est)})')
    if not execute:
        return est

    # 优先 uv（uv 创建的 venv 没有 pip），回退 venv 自带 pip
    uv = shutil.which('uv')
    if uv:
        cmd = [uv, 'pip', 'uninstall', '--python', str(venv_python)] + to_remove
    else:
        cmd = [str(venv_python), '-m', 'pip', 'uninstall', '-y'] + to_remove
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f'  [失败] 卸载出错: {(r.stderr or r.stdout).strip()[:300]}')
            print('  可手动执行: uv sync  （按 pyproject.toml 精确同步，会移除多余包）')
            return 0
        print(f'  已卸载: {", ".join(to_remove)}')
    except FileNotFoundError:
        print('  [失败] 找不到 uv / pip。请手动执行: uv sync')
        return 0
    return est


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='清理旧版本地翻译方案（MarianMT/opus-mt）的缓存，默认 dry-run')
    parser.add_argument('--yes', action='store_true',
                        help='实际执行删除（默认只预览）')
    args = parser.parse_args()
    execute = args.yes

    print(f'项目根: {PROJECT_ROOT}')
    print(f'模式: {"实际执行" if execute else "dry-run 预览（加 --yes 执行）"}')

    freed = plan_hf_cleanup(execute)
    freed += plan_venv_cleanup(execute)

    print('\n== 汇总 ==')
    print(f'预计/已回收: {human(freed)}')
    print('未动（防误删）: uv/pip 下载缓存（跨项目共享）、系统 Python、'
          '其他项目的 venv、HF 缓存里的其他模型')
    if not execute:
        print('\n这是预览。确认无误后执行: python cleanup_legacy_models.py --yes')


if __name__ == '__main__':
    main()
