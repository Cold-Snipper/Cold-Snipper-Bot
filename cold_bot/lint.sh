#!/bin/bash
set -e

black .
flake8 .
