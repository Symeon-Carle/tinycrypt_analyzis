import csv
import json
import re
import subprocess
import tempfile
from itertools import chain
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Hashable,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Tuple,
    TypeVar,
    Union,
)

# The json code coverage export follows the following format
# Root: dict => Root Element containing metadata
# -- Data: array => Homogeneous array of one or more export objects
#   -- Export: dict => Json representation of one CoverageMapping
#     -- Files: array => List of objects describing coverage for files
#       -- File: dict => Coverage for a single file
#         -- Branches: array => List of Branches in the file
#           -- Branch: dict => Describes a branch of the file with counters
#         -- Segments: array => List of Segments contained in the file
#           -- Segment: dict => Describes a segment of the file with a counter
#         -- Expansions: array => List of expansion records;
#           -- Expansion: dict => Object that descibes a single expansion
#             -- CountedRegion: dict => The region to be expanded
#             -- TargetRegions: array => List of Regions in the expansion
#               -- CountedRegion: dict => Single Region in the expansion
#             -- Branches: array => List of Branches in the expansion
#               -- Branch: dict => Describes a branch in expansion and counters
#         -- Summary: dict => Object summarizing the coverage for this file
#           -- LineCoverage: dict => Object summarizing line coverage
#           -- FunctionCoverage: dict => Object summarizing function coverage
#           -- RegionCoverage: dict => Object summarizing region coverageFilenames
#           -- BranchCoverage: dict => Object summarizing branch coverage
#     -- Functions: array => List of objects describing coverage for functions
#       -- Function: dict => Coverage info for a single function
#         -- Filenames: array => List of filenames that the function relates to
#   -- Summary: dict => Object summarizing the coverage for the entire binary
#     -- LineCoverage: dict => Object summarizing line coverage
#     -- FunctionCoverage: dict => Object summarizing function coverage
#     -- InstantiationCoverage: dict => Object summarizing inst. coverage
#     -- RegionCoverage: dict => Object summarizing region coverage
#     -- BranchCoverage: dict => Object summarizing branch coverage

# {
#     "version": "2.0.0",
#     "type": "llvm.coverage.json.export",
#     "data": [
#         {
#             "files": [
#                 {   
#                     "filename": "",
#                     "segments": [[
#                         1, # line
#                         1, # column
#                         1, # count
#                         True, # has count
#                         True, # is region entry
#                         True, # is gap region
#                     ]],
#                     "branches": [[
#                         1, # line start
#                         1, # column start
#                         1, # line end
#                         1, # column end
#                         1, # execution count
#                         1, # false execution count
#                         "", # file ID
#                         "", # expanded file ID
#                         1, # region kind
#                     ]],
#                     "expansion": [
#                         {
#                             "filenames": ["", "", ""],
#                             "source_region": [
#                                 # Region.LineStart,
#                                 # Region.ColumnStart,
#                                 # Region.LineEnd,
#                                 # Region.ColumnEnd,
#                                 # Region.ExecutionCount,
#                                 # Region.FileID,
#                                 # Region.ExpandedFileID,
#                                 # Region.Kind
#                             ],
#                             "target_regions": [[
#                                 # Region.LineStart,
#                                 # Region.ColumnStart,
#                                 # Region.LineEnd,
#                                 # Region.ColumnEnd,
#                                 # Region.ExecutionCount,
#                                 # Region.FileID,
#                                 # Region.ExpandedFileID,
#                                 # Region.Kind
#                             ]],
#                             "branches": [[
#                                 1, # line start
#                                 1, # column start
#                                 1, # line end
#                                 1, # column end
#                                 1, # execution count
#                                 1, # false execution count
#                                 "", # file ID
#                                 "", # expanded file ID
#                                 1, # region kind
#                             ]]
#                         }
#                     ],
#                     "summary": {
#                         "lines": {
#                             "count": 1,
#                             "covered": 1,
#                             "percent": 100.0
#                         },
#                         "functions": {
#                             "count": 1,
#                             "covered": 1,
#                             "percent": 100.0
#                         },
#                         "instantiations": {
#                             "count": 1,
#                             "covered": 1,
#                             "percent": 100.0
#                         },
#                         "regions": {
#                             "count": 1,
#                             "covered": 1,
#                             "notcovered": 0,
#                             "percent": 100.0
#                         },
#                         "branches": {
#                             "count": 1,
#                             "covered": 1,
#                             "notcovered": 0,
#                             "percent": 100.0
#                         }
#                     }
#                 }
#             ],
#             "totals": {
#                 "lines": {
#                     "count": 1,
#                     "covered": 1,
#                     "percent": 100.0
#                 },
#                 "functions": {
#                     "count": 1,
#                     "covered": 1,
#                     "percent": 100.0
#                 },
#                 "instantiations": {
#                     "count": 1,
#                     "covered": 1,
#                     "percent": 100.0
#                 },
#                 "regions": {
#                     "count": 1,
#                     "covered": 1,
#                     "notcovered": 0,
#                     "percent": 100.0
#                 },
#                 "branches": {
#                     "count": 1,
#                     "covered": 1,
#                     "notcovered": 0,
#                     "percent": 100.0
#                 }
#             },
#             "functions": [
#                 {
#                     "name": "blabla",
#                     "count": 1,
#                     "regions": [[
#                         # Region.LineStart,
#                         # Region.ColumnStart,
#                         # Region.LineEnd,
#                         # Region.ColumnEnd,
#                         # Region.ExecutionCount,
#                         # Region.FileID,
#                         # Region.ExpandedFileID,
#                         # Region.Kind
#                     ]],
#                     "branches": [[
#                         1, # line start
#                         1, # column start
#                         1, # line end
#                         1, # column end
#                         1, # execution count
#                         1, # false execution count
#                         "", # file ID
#                         "", # expanded file ID
#                         1, # region kind
#                     ]],
#                     "filenames": [""]
#                 }
#             ]
#         }
#     ]
# }

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


def group_by(key_func: Callable[[V], K], values: Iterable[V]) -> Dict[K, List[V]]:
    res = {}  # type: Dict[K, List[V]]
    for elem in values:
        key = key_func(elem)
        res.setdefault(key, []).append(elem)
    return res

InfoDict = Dict[str, str]
ParsedCSV = List[InfoDict]


def parse_tis_csv(file: Path) -> ParsedCSV:
    with file.open(encoding="utf-8", errors="surrogateescape") as f:
        return list(csv.DictReader(f, skipinitialspace=True))


Summary = NamedTuple("Summary", [("covered", int), ("count", int)])  # total


def aggregate_line_coverage(statments: ParsedCSV) -> Dict[Path, Summary]:
    statements_by_line = group_by(
        lambda s: (Path(s["File"]), int(s["Line"])), statements
    )

    res = {}  # type: Dict[Path, Summary]
    for (file, line), statements_info in statements_by_line.items():
        summary = res.get(file, Summary(count=0, covered=0))
        summary = summary._replace(count=summary.count + 1)
        if any(info["Reachable"] == "reachable" for info in statements_info):
            summary = summary._replace(covered=summary.covered + 1)

        res[file] = summary

    return res


DIGITS = re.compile(r"([0-9]+)")

NaturalSortKey = Tuple[int, Union[str, int]]


def string_natural_sort(s: str) -> Iterator[NaturalSortKey]:
    for text in DIGITS.split(s):
        # re.split() occasionnaly gives back empty strings at the beginning or
        # end of the sequence, it's easier if we just ignore them here
        if text:
            if text.isdigit():
                yield (1, int(text))
            else:
                yield (2, text.lower())


def path_natural_sort(p: Path) -> List[List[NaturalSortKey]]:
    return [list(string_natural_sort(s)) for s in p.parts]


RESULTS_JSON_RE = re.compile(r"(.+)_results")


def guess_analysis_name(results: Path) -> str:
    m = RESULTS_JSON_RE.fullmatch(results.stem)
    if m is not None:
        return m.group(1)
    else:
        return results.name


def find_analyses_prefixes(folder: Path) -> Iterator[Path]:
    for path in folder.glob("**/*_results.json"):
        analysis = guess_analysis_name(path)
        yield folder / path.with_name(analysis).relative_to(folder)


def aggregate_function_coverage(functions: ParsedCSV) -> Dict[Path, Dict[str, bool]]:
    res = {}  # type: Dict[Path, Dict[str, bool]]
    for info in functions:
        if info["Is libc"] == "libc:yes":
            continue
        file = Path(info["File"])
        name = info["Function"]
        reachable = info["Is reachable"] == "reachable"
        covered_functions = res.setdefault(file, {})
        covered_functions[name] = covered_functions.get(name, False) or reachable

    return res


def iter_relevant_files(csv: ParsedCSV) -> Iterable[Path]:
    for info in csv:
        if info["Is libc"] == "yes":
            continue
        yield Path(info["File"])


def convert_to_llvm_coverage(
    functions: ParsedCSV,
    files: ParsedCSV,
    statements: ParsedCSV,
) -> Dict:
    relevant_files = sorted(set(iter_relevant_files(files)), key=path_natural_sort)
    lines_coverage = aggregate_line_coverage(statements)
    functions_coverage = aggregate_function_coverage(functions)
    statements_per_file = group_by(
        lambda s: Path(s["File"]),
        statements
    )
    return {
        "version": "2.0.0",
        "type": "llvm.coverage.json.export",
        "data": [
            {
                "files": [
                    convert_file(file, lines_coverage, statements_per_file, functions_coverage)
                    for file in relevant_files
                ],
                "functions": [],  # TODO: figure out what needs to go there
            }
        ],
    }


def convert_file(
    path: Path,
    lines_coverage: Dict[Path, Summary],
    statements_per_file: Dict[Path, List[InfoDict]],
    functions_coverage: Dict[Path, Dict[str, bool]],
) -> dict:
    functions_covered = functions_coverage.get(path, {})
    function_summary = Summary(
        count=len(functions_covered), covered=sum(functions_covered.values())
    )
    statments = statements_per_file.get(path, [])
    return {
        "filename": str(path),
        "segments": [],
        "summary": {
            "lines": lines_coverage.get(path, Summary(count=0, covered=0))._asdict(),
            "functions": function_summary._asdict(),
        },
    }

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("folder", type=Path)

    args = parser.parse_args()

    for prefix in find_analyses_prefixes(args.folder):
        functions = parse_tis_csv(prefix.with_name(prefix.name + "_functions.csv"))
        files = parse_tis_csv(prefix.with_name(prefix.name + "_files.csv"))
        statements = parse_tis_csv(prefix.with_name(prefix.name + "_statements.csv"))
        llvm_coverage = convert_to_llvm_coverage(functions, files, statements)
        with prefix.with_name(prefix.name + "_coverage.json").open("w") as f:
            json.dump(llvm_coverage, f, indent=4)
