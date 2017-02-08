#!/bin/bash

# I'm sure there's a better way to do this. anrbot.py uses some
# relative paths, so it should be run from the directory in which the
# script exists. 

cd $(dirname $0)
./anrbot.py $1
