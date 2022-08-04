import json
import pprint
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from itertools import chain, count, cycle, starmap
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Hashable,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


def group_by(values: Iterable[V], key_func: Callable[[V], K]) -> Dict[K, List[V]]:
    res = {}  # type:  Dict[K, List[V]]
    for elem in values:
        key = key_func(elem)
        res.setdefault(key, []).append(elem)
    return res


Results = NamedTuple(
    "Results", [("alarms", List[dict]), ("degeneration", Optional[dict])]
)


def parse_alarms(results: dict) -> List[dict]:
    return results.get("alarms", {}).get("list", [])


def parse_degeneration(results: dict) -> Optional[dict]:
    if results.get("degeneration", {}).get("status") != "NOT OK":
        return None

    return results.get("degeneration")


def parse_json(results: dict) -> Results:
    return Results(
        alarms=parse_alarms(results), degeneration=parse_degeneration(results)
    )


def parse_folder(folder: Path) -> Iterator[Tuple[Path, Results]]:
    for path in folder.glob("**/*_results.json"):
        with path.open("r") as file:
            result_json = json.load(file)
        yield path, parse_json(result_json)


RESULTS_JSON_RE = re.compile(r"(.+)_results")


def guess_analysis_name(results: Path) -> str:
    m = RESULTS_JSON_RE.fullmatch(results.stem)
    if m is not None:
        return m.group(1)
    else:
        return results.name


def dump_many_as_maven_surefire(
    results_per_file: Dict[Path, Results]
) -> Dict[Path, ET.ElementTree]:
    res = {}
    for file, results in results_per_file.items():
        element = dump_one_as_maven_surefire(file, results)
        tree = ET.ElementTree(element=element)
        name = guess_analysis_name(file)
        xml_path = file.parent / "{}.xml".format(name)
        res[xml_path] = tree

    return res


def dump_one_as_maven_surefire(file: Path, results: Results) -> ET.Element:
    name = guess_analysis_name(file)
    testsuite = ET.Element(
        "testsuite",
        attrib={
            "name": name,
            "tests": "0",
            "errors": str(int(results.degeneration is not None)),
            "skipped": "0",
            "failures": str(len(results.alarms)),
        },
    )
    for alarm in results.alarms:
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            attrib={
                "name": "Alarm in {}".format(file),
                "time": "0",  # required by schematestcase =
            },
        )
        error = ET.SubElement(testcase, "error")
        error.text = json.dumps(alarm, indent=4)

    if results.degeneration is not None:
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            attrib={
                "name": "Degeneration in {}".format(file),
                "time": "0",  # required by schematestcase =
            },
        )
        error = ET.SubElement(testcase, "error")
        error.text = json.dumps(results.degeneration, indent=4)

    return testsuite


def make_unique(file: Path) -> Path:
    numbers = count(start=1)
    names_deduped = map(
        lambda i: (
            file.parent / "{}-{}{}".format(file.stem, i, "".join(file.suffixes))
        ),
        numbers,
    )
    names_conscidered = chain([file], names_deduped)
    available_names = filter(lambda p: not p.exists(), names_conscidered)
    return next(available_names)


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description=(
            "Convert result JSONs into Maven SureFire XMLs. "
            "Files named *_result.json are searched recursively from the given "
            "folder. Generated files are named {analysis}.xml and placed next "
            "to their json counterpart"
        ),
    )
    parser.add_argument(
        "folder", type=Path, help="Folder searched recursively for *_results.json files"
    )
    args = parser.parse_args()
    results = dict(parse_folder(args.folder))
    trees = dump_many_as_maven_surefire(results)
    for filename, tree in trees.items():
        filename = make_unique(filename)
        tree.write(str(filename))
