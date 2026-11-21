# flpcheck

[![tests](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml/badge.svg)](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml)

[English](README.md) | **简体中文**

找出 FL Studio 工程里丢了的采样。

FL Studio 用绝对路径记采样，又没有 Ableton 的 *Collect All and Save*。工程一挪、
采样库一整理、或者打开别人发来的工程，满屏都是 *sample not found*，而且不告诉你
丢的是哪几个。

`flpcheck` 读一遍 `.flp`，把里面引用的采样全列出来，标出哪些已经不在原位，再帮你
在硬盘上把候选找回来。

```
$ flpcheck check song.flp --search-root "E:\Samples"

song.flp
  samples: 8 referenced, 5 ok, 2 missing, 1 unresolved

  ✗ bass_final_v3.wav
      referenced as: D:\Old\Samples\bass_final_v3.wav
      found:
        E:\Samples\Bass\bass_final_v3.wav
  ✗ riser_ambient.wav
      referenced as: D:\Old\Samples\riser_ambient.wav
      not found in the search roots

  ? 2Hihat.wav
      referenced as: %FLStudioFactoryData%\drums\pack\2Hihat.wav
      not checked: this path uses an FL Studio macro. Map it with --macro NAME=DIR
```

结果分三种状态，不是两种：

| 标记 | 状态 | 含义 |
| --- | --- | --- |
| — | ok | 文件就在原位 |
| ✗ | missing | 绝对路径，但文件不在了 |
| ? | unresolved | 宏路径，在你说明宏指向哪之前查不了 |

为什么要多这一个「未检查」？因为工厂包的采样是用 `%FLStudioFactoryData%` 这种宏记的，
而真实工程里这类引用比盘符路径多好几倍。全算成「缺失」，你一打开就是几百个红叉，
全是假的。所以查不了的就老实说查不了。

## 它不会碰你的文件

`flpcheck` 只以只读方式打开 `.flp`，打印一份报告就结束。没有修复模式，不就地改，
也不碰任何音频文件。

改 `.flp` 的字节是最快毁掉别人工程的办法。v0.1 只负责把情况说清楚。

## 安装

还没发到 PyPI，从源码装：

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
uv pip install -e .
# 或者: pip install -e .
```

Python 3.10 以上，无运行时依赖。

## 用法

### 查工程缺哪些采样

```bash
flpcheck check song.flp
flpcheck check *.flp
flpcheck check ~/Projects/song.flp --search-root "E:\Samples" --search-root "D:\Downloads"
```

| 参数 | 作用 |
| --- | --- |
| `--search-root DIR` | 去哪儿找丢失的采样。可写多次。 |
| `--macro NAME=DIR` | 某个 FL Studio 宏指向的目录，给了才能查这类引用。可写多次。 |
| `--no-search` | 只报告，不去找候选。 |
| `--max-candidates N` | 每个采样给几个候选（默认 `3`）。 |
| `--max-index-files N` | 每个搜索根最多索引多少文件（默认 `200000`）。 |
| `--json` | 输出 JSON，给脚本用。 |

要查工厂包，把宏指到 FL Studio 的数据目录：

```bash
flpcheck check song.flp --macro "%FLStudioFactoryData%=C:\Program Files\Image-Line\FL Studio 21\Data"
```

### 查某个采样被哪些工程用过

```bash
flpcheck find ~/Projects --sample bass_final_v3
flpcheck find ~/Projects --sample serum --exact
```

准备删采样之前先查一下，或者想不起那段 loop 落在哪个工程里了。

### 退出码

| 码 | 意思 |
| --- | --- |
| `0` | 没缺 |
| `1` | 有采样缺失 |
| `2` | 文件读不了 |

「未检查」不算失败。退出码 `1` 只表示本该在盘上的文件不在。

## 怎么实现的

`.flp` 是二进制格式，不是文本。v0.1 没上完整解析器，而是把文件按 UTF-16LE 解码，
再去找长得像路径的字符串——FL Studio 本来就是这么存的。所以你在 `.flp` 里直接
grep 文本，什么也搜不到。

下面三个细节比看上去重要得多，而且每一个都是拿真实工程跑出来的，不是合成数据：

- **奇偶两种字节位都得扫。** FL Studio 的事件头是「1 字节 id + 变宽长度」，字符串
  可能从偶数字节起，也可能从奇数字节起。我手上有个工程，6 条路径里就有 1 条起在
  奇数位，只扫偶数位会悄悄漏掉，还不报错。
- **路径是挨着存的。** 一条 `.wav` 后面经常紧跟着下一条字符串，所以匹配器不能在
  扩展名之后要求分隔符。顺带一个坑：`...riser.wav` 后面接 `E:\...`，一不留神就把
  `.wavE` 读成扩展名 `.wave`。
- **宏路径得先认出来。** 不知道数据目录，`%FLStudioFactoryData%\...` 就解析不了，
  但至少得看见它。看不见的话，这些工程会显示成「一条采样都没有」。

搜索只走一遍。`--search-root` 遍历一次建好文件名索引，之后查 40 个缺失采样就是
40 次查表，不会把采样库来回翻 40 遍。

## 已知问题

v0.1 明确不做的：

- **宏路径要手动指。** 不给 `--macro` 就只报「未检查」，不会瞎报「缺失」。工厂数据
  目录没有自动探测。
- **字符串扫描是猜的，不是解析。** 理论上遇到异常的二进制内容可能误报。真实工程上
  更常见的是漏报。
- **还看不了插件。** 要列一个工程用了哪些插件，得上真正的解析器，见后续计划。
- **不能修。** 候选路径打印给你，自己回 FL Studio 里重新定位。

## 后续计划

- [ ] 自动找 `%FLStudioFactoryData%`。我测试那台机器上它指的是 FL Studio 安装目录
      （有 `FL64.exe` 那个），不是里面的 `Data` 子目录，别照着 `Data` 写死。
- [ ] 插件清单，用 [PyFLP](https://github.com/demberto/PyFLP)
- [ ] 认出保存工程的 FL Studio 版本
- [ ] 可选：输出一份重定位方案，不只打印候选路径

## 开发

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
python -m unittest discover -s tests -t . -v
```

测试只依赖标准库，不用装别的。

提取器在 60 个真实工程上跑过：194 条不重复的采样引用，没有一条 `.wav` 类字符串
被漏掉。

## 许可证

MIT，见 [LICENSE](LICENSE)。
