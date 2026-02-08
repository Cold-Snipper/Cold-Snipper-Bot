#!/bin/bash
# Compile the Java UI. Run from java_ui/ or project root.
set -e
cd "$(dirname "$0")"
javac -d out src/Main.java
echo "Build OK. Run: java -cp out Main [port]"
