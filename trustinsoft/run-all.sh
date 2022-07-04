#!/bin/bash


##############################################################################
# Working directory
##############################################################################

cd "$(dirname "$0")"


##############################################################################
# Cleaning old results
##############################################################################

rm -rf tis_report.html _results

mkdir -p _results


##############################################################################
# Analysis of all tests
##############################################################################

function run_test_analysis {
  analysis_name="$1"

  opt=(
    -tis-config-load config.json
    -tis-config-select "${analysis_name}"
    -tis-report
    -save "_results/${analysis_name}.save"
  )

  tis-analyzer "${opt[@]}"

  cat <<EOF > "_results/${analysis_name}_info.json"
{
    "tis-analyzer-version": "$(tis-analyzer --version)",
    "cmd": "tis-analyzer -tis-config-load config.json -tis-config-select ${analysis_name}"
}
EOF
}

export -f run_test_analysis

NB_TESTS=$(grep \"name\" config.json | grep -v NO_CONFIG | wc -l)
parallel -j 6 run_test_analysis ::: $(seq 1 $NB_TESTS)


##############################################################################
# Computing the results
##############################################################################

tis-report _results
