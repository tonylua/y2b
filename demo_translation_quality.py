"""
演示 sentence 模式相比逐条翻译的改进：
- 句子完整性（避免半句翻译）
- 中文断句（按标点断而非英文条目边界）
- 术语一致性（glossary）
"""
import sys
import io
from datetime import timedelta
from src.utils.translate_srt import SRTTranslator

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def demo_sentence_vs_fragment():
    """对比：碎片逐条翻译 vs 整句翻译"""
    print("\n=== 场景1：YouTube 碎片化字幕 ===")
    print("英文原文（3条碎片）:")
    fragments = [
        "So what we're going to do",
        "is take this array",
        "and sort it in place."
    ]
    for i, f in enumerate(fragments, 1):
        print(f"  [{i}] {f}")

    print("\n如果逐条翻译（旧方案，每条独立无上下文）：")
    old_results = [
        "所以我们要做的",
        "是采取这个数组",  # 机械直译
        "并就地排序它。"
    ]
    for i, r in enumerate(old_results, 1):
        print(f"  [{i}] {r}")
    print("  ❌ 问题：读起来支离破碎，「采取数组」不是人话")

    print("\n✅ sentence 模式（先合并整句再翻译）：")
    full_sentence = " ".join(fragments)
    print(f"  合并后: {full_sentence}")
    print(f"  翻译为: 那么我们要做的是获取这个数组并就地排序。")
    print("  然后按中文标点重切成适合显示的行。")


def demo_chinese_resegment():
    """对比：硬套英文断点 vs 按中文标点重切"""
    print("\n\n=== 场景2：中文重切（按意群断句） ===")
    en = "First, we need to initialize the array with default values, then iterate through each element."
    cn_raw = "首先，我们需要用默认值初始化数组，然后遍历每个元素。"

    print(f"英文: {en}")
    print(f"中文: {cn_raw}")
    print(f"\n如果硬套英文的时间轴切点（可能在逗号前后切开）：")
    print("  [1] 首先，我们需要用默认值初")
    print("  [2] 始化数组，然后遍历每个元")
    print("  [3] 素。")
    print("  ❌ 切在半个词中间，无法阅读")

    print(f"\n✅ 按中文标点断句（max_line_chars=20）：")
    print("  [1] 首先，我们需要用默认值初始化数组，")
    print("  [2] 然后遍历每个元素。")
    print("  各行时间轴按字数比例从原句跨度重新分配。")


def demo_glossary():
    """术语表确保技术词汇翻译一致"""
    print("\n\n=== 场景3：术语表（config/glossary.json） ===")
    print("无术语表: We pass a callback to the array method.")
    print("  → 我们向数组方法传递一个回叫函数。")
    print("  ❌ callback 被译成「回叫」（不规范）")

    print("\n✅ 有术语表 { \"callback\": \"回调\", \"array\": \"数组\" }:")
    print("  → 我们向数组方法传递一个回调函数。")
    print("  翻译后强制替换术语，保证一致性。")


def demo_live_model():
    """加载真实模型演示（可选，需要模型下载完成）"""
    print("\n\n=== 可选：真实模型演示 ===")
    try:
        tr = SRTTranslator(
            translate_mode='sentence',
            domain=None,
            glossary={'array': '数组', 'callback': '回调'}
        )

        # 模拟碎片字幕
        class Sub:
            def __init__(self, idx, start, end, text):
                self.index = idx
                self.start = timedelta(seconds=start)
                self.end = timedelta(seconds=end)
                self.content = text

        subs = [
            Sub(1, 0.0, 1.2, "So what we're going to do"),
            Sub(2, 1.2, 2.4, "is use a callback function"),
            Sub(3, 2.4, 3.6, "to filter the array.")
        ]

        print("输入（3条碎片）:")
        for s in subs:
            print(f"  [{s.index}] {s.content}")

        print("\n正在调用模型翻译（sentence 模式）...")
        result = tr._translate_sentence_mode(subs, bilingual=False)

        print(f"\n输出（{len(result)}条，按中文重切）:")
        for r in result:
            print(f"  [{r.index}] {r.start} --> {r.end}")
            print(f"      {r.content}")

    except Exception as e:
        print(f"模型未加载或出错: {e}")
        print("跳过真实模型演示（前面的逻辑演示已足够说明改进）")


if __name__ == '__main__':
    demo_sentence_vs_fragment()
    demo_chinese_resegment()
    demo_glossary()

    if '--model' in sys.argv:
        demo_live_model()
    else:
        print("\n\n提示：加 --model 参数可运行真实模型演示（需首次下载模型）")
