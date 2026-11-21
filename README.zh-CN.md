# flpcheck

[![tests](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml/badge.svg)](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml)

[English](README.md) | **简体中文**

找出你的 FL Studio 工程里丢失的采样。

FL Studio 用绝对路径引用采样，也没有 Ableton 那样的 *Collect All and Save*。
移动工程文件夹、整理采样库、或者打开合作方发来的工程，你会看到满屏的
*sample not found*，而且完全不知道**丢的是哪几个**。

`flpcheck` 读取 `.flp`，列出它引用的所有采样，告诉你哪些已经不在工程期望的位置，
并在你的硬盘上帮你把它们找回来。

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

三种状态，刻意区分：

| 标记 | 状态 | 含义 |
| --- | --- | --- |
| — | ok | 文件就在工程期望的位置 |
| ✗ | missing | 这是绝对路径，但文件已经不在了 |
| ? | unresolved | 这是宏路径，在你说明该宏指向哪里之前**无法检查** |

第三种状态存在的原因：工厂包采样是通过 `%FLStudioFactoryData%` 这类宏引用的。
在真实工程里，这类引用的数量是盘符路径的好几倍。把它们报成「缺失」会误报上百个文件，
所以报表里如实标成「未检查」。

## 安全性

**`flpcheck` 永远不会写入你的工程文件或采样文件。** 它只以只读方式打开 `.flp`
并打印报告。没有修复模式，没有就地编辑，也不会碰任何音频文件。

这是刻意的取舍：改写 `.flp` 的字节是最快毁掉别人工作的方式。v0.1 只负责把真相告诉你。

## 安装

`flpcheck` 尚未发布到 PyPI，请从源码安装：

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
uv pip install -e .
# 或者: pip install -e .
```

需要 Python 3.10+，无运行时依赖。

## 用法

### 检查工程里缺失的采样

```bash
flpcheck check song.flp
flpcheck check *.flp
flpcheck check ~/Projects/song.flp --search-root "E:\Samples" --search-root "D:\Downloads"
```

| 参数 | 含义 |
| --- | --- |
| `--search-root DIR` | 在哪个目录里搜索丢失的采样。可重复。 |
| `--macro NAME=DIR` | 某个 FL Studio 宏指向的目录，给出后这些引用才能被检查。可重复。 |
| `--no-search` | 只报告，跳过候选搜索。 |
| `--max-candidates N` | 每个采样显示几个候选（默认 `3`）。 |
| `--max-index-files N` | 每个搜索根最多索引多少文件（默认 `200000`）。 |
| `--json` | 机器可读输出。 |

要检查工厂包引用，把宏指向 FL Studio 的数据目录：

```bash
flpcheck check song.flp --macro "%FLStudioFactoryData%=C:\Program Files\Image-Line\FL Studio 21\Data"
```

### 查询哪些工程用到了某个采样

```bash
flpcheck find ~/Projects --sample bass_final_v3
flpcheck find ~/Projects --sample serum --exact
```

适合在准备删除某个采样之前确认一下，或者想不起那段 loop 到底落在哪个工程里的时候用。

### 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 没有缺失 |
| `1` | 至少有一个采样缺失 |
| `2` | 文件读取失败 |

宏引用「未检查」**不算**失败：退出码 `1` 特指「本该在磁盘上的文件不在」。

## 工作原理

`.flp` 是二进制格式。v0.1 没有引入完整的解析器，而是把文件按 UTF-16LE 解码后
匹配「长得像路径」的字符串——FL Studio 就是这么存采样路径的。这也是为什么
直接用 ASCII grep 搜原始字节什么都搜不到。

有三个细节比它们看起来重要得多，而且每一个都是在**真实工程**上发现的 bug，
不是合成数据能测出来的：

- **两种字节对齐都要扫。** FL Studio 的事件头是「1 字节 id + 变宽长度」，
  所以字符串可能从偶数字节开始，也可能从**奇数字节**开始。某个真实工程里
  6 条采样路径中就有 1 条起始于奇数偏移，只扫偶数对齐会静默漏掉它。
- **路径是紧挨着存的。** 一条 `.wav` 路径后面往往紧跟着下一个字符串，所以
  匹配器不能在扩展名之后要求分隔符。相关的坑：`...riser.wav` 后面紧跟 `E:\...`
  时，前半段会被读成扩展名 `.wave`。
- **宏路径是一等公民。** 不知道 FL Studio 的数据目录，`%FLStudioFactoryData%\...`
  就无法解析，但**必须能识别出来**——否则这些工程看起来像是完全没有采样。

搜索只索引一次：`--search-root` 只遍历一遍并建立文件名索引，所以查 40 个缺失
采样是 40 次字典命中，而不是把整个采样库走 40 遍。

## 局限性

以下是 v0.1 明确**不做**的事：

- **宏引用需要手工映射。** 不给 `--macro` 时它们报为「未检查」，绝不报成「缺失」。
  工厂数据目录不会自动探测。
- **字符串扫描是启发式的。** 理论上，含有异常二进制数据的文件可能产生误报。
  在真实工程上，漏报比误报更可能发生。
- **还不支持插件检测。** 列出一个工程用了哪些插件需要真正的解析器，见路线图。
- **没有修复功能。** 候选路径打印给你，由你在 FL Studio 里重新定位。

## 路线图

- [ ] 自动探测 `%FLStudioFactoryData%` 目录。在测试用的那台机器上，它指向的是
      FL Studio 安装目录（含 `FL64.exe` 的那个），**不是**它的 `Data` 子目录——
      写死猜测之前值得知道这一点。
- [ ] 插件清单，基于 [PyFLP](https://github.com/demberto/PyFLP)
- [ ] 识别保存该工程的 FL Studio 版本
- [ ] 可选：输出一份重定位方案，而不只是打印候选路径

## 开发

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
python -m unittest discover -s tests -t . -v
```

测试套件只依赖标准库，不需要额外安装任何东西。

提取器已在 60 个真实工程上验证：194 条不重复的采样引用，
没有任何 `.wav` 类字符串被漏掉。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
