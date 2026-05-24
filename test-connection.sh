#!/usr/bin/env bash

source .env
cat login.json | nc localhost $SRV_PORT