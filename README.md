# flpcheck

[![tests](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml/badge.svg)](https://github.com/krinoho2007/flpcheck/actions/workflows/tests.yml)

Find the samples your FL Studio project is missing.

FL Studio references samples by absolute path and has no equivalent of
Ableton's *Collect All and Save*. Move a project folder, change a sample
library, or open a collaborator's project, and you get a wall of
*sample not found* — with no indication of **which** samples are gone.

`flpcheck` reads a `.flp`, lists every sample it references, tells you which
ones are no longer where the project expects them, and looks for them
elsewhere on your disk.

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

Three states, deliberately distinct:

| Mark | State | Meaning |
| --- | --- | --- |
| — | ok | The file is exactly where the project expects it. |
| ✗ | missing | The path is absolute and the file is not there. |
| ? | unresolved | The path uses an FL Studio macro, so it **cannot** be checked until you say where that macro points. |

The third state exists because factory-pack samples are referenced through
macros such as `%FLStudioFactoryData%`. On real projects those outnumber
drive-letter paths several times over. Reporting them as "missing" would be a
false alarm on hundreds of files, so they are reported as unchecked instead.

## Safety

**`flpcheck` never writes to your project files or your samples.** It opens
`.flp` files read-only and prints a report. There is no repair mode, no
in-place editing, and nothing that touches your audio files.

That is deliberate: rewriting `.flp` bytes is the fastest way to destroy
someone's work. v0.1 only tells you the truth.

## Install

`flpcheck` is not on PyPI yet. Install from a clone:

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
uv pip install -e .
# or: pip install -e .
```

Requires Python 3.10+. No runtime dependencies.

## Usage

### Check projects for missing samples

```bash
flpcheck check song.flp
flpcheck check *.flp
flpcheck check ~/Projects/song.flp --search-root "E:\Samples" --search-root "D:\Downloads"
```

| Flag | Meaning |
| --- | --- |
| `--search-root DIR` | Directory to search for lost samples. Repeatable. |
| `--macro NAME=DIR` | Where an FL Studio macro points, so those references can be checked. Repeatable. |
| `--no-search` | Only report; skip the candidate search. |
| `--max-candidates N` | Candidates shown per sample (default `3`). |
| `--max-index-files N` | Cap on files indexed per root (default `200000`). |
| `--json` | Machine-readable output. |

To check factory-pack references, point the macro at FL Studio's data folder:

```bash
flpcheck check song.flp --macro "%FLStudioFactoryData%=C:\Program Files\Image-Line\FL Studio 21\Data"
```

### Find which projects use a sample

```bash
flpcheck find ~/Projects --sample bass_final_v3
flpcheck find ~/Projects --sample serum --exact
```

Useful when a sample is about to be deleted, or when you cannot remember
which project that loop ended up in.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Nothing missing. |
| `1` | At least one sample is missing. |
| `2` | The file could not be read. |

Unresolved macro references do **not** count as failures: exit code `1` means
a file that should be on disk is not.

## How it works

`.flp` is a binary format. Rather than depend on a full parser in v0.1,
`flpcheck` decodes the file as UTF-16LE and matches path-shaped strings —
which is how FL Studio stores them. That is why a plain ASCII grep over the
raw bytes finds nothing.

Three details matter more than they look, and each one was a bug found on
real projects rather than synthetic ones:

- **Both byte alignments are scanned.** An FL Studio event header is a
  one-byte id plus a variable-width length, so a string can start at an even
  *or* an odd offset. One of six sample paths in a real project started odd
  and was invisible to an aligned-only scan.
- **Paths are stored back to back.** A `.wav` path is often followed
  immediately by the next string, so the matcher cannot require a separator
  after the file extension. Related trap: `...riser.wav` followed by `E:\...`
  reads as the extension `.wave` if you are not careful.
- **Macro paths are first-class.** `%FLStudioFactoryData%\...` cannot be
  resolved without knowing FL Studio's data directory, but it must still be
  found — otherwise those projects look like they contain no samples at all.

Searching is indexed once: `--search-root` is walked a single time and indexed
by filename, so looking up 40 missing samples is 40 dictionary hits rather than
40 full traversals of your library.

## Limitations

Be aware of what v0.1 does not do:

- **Macro references need manual mapping.** Without `--macro`, they are
  reported as unresolved, never as missing. The factory-data location is not
  auto-detected.
- **String scanning is heuristic.** A file containing unusual binary data
  could theoretically produce a false positive. False negatives are more
  likely than false positives on real projects.
- **No plugin detection yet.** Listing the plugins a project uses needs a
  real parser; see the roadmap.
- **No repair.** The candidate paths are printed for you to relocate in
  FL Studio.

## Roadmap

- [ ] Auto-detect the `%FLStudioFactoryData%` directory. On the machine this
      was tested on it resolved to the FL Studio install folder (the one
      containing `FL64.exe`), **not** to its `Data` subfolder — worth knowing
      before hardcoding a guess.
- [ ] Plugin inventory, via [PyFLP](https://github.com/demberto/PyFLP)
- [ ] Detect the FL Studio version that saved the project
- [ ] Optional: emit a relocation plan instead of just printing candidates

## Development

```bash
git clone https://github.com/krinoho2007/flpcheck
cd flpcheck
python -m unittest discover -s tests -t . -v
```

The test suite uses only the standard library, so no install step is needed.

The extractor was validated against 60 real projects: 194 distinct sample
references, with zero `.wav`-like strings left unmatched.

## License

MIT — see [LICENSE](LICENSE).
