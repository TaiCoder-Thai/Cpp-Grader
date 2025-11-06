#!/bin/bash
set -e

cargo build --release

./target/release/submission_server
