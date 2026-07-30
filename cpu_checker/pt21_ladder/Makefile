# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

CC ?= cc
CCOMP ?= ccomp
CFLAGS ?= -O2
STRICT_CFLAGS := -std=c11 -Wall -Wextra -Wconversion -Werror -pedantic
CCOMP_CFLAGS := -O -std=c11 -Wall

.PHONY: all test ccomp clean

all: pt21_ladder_bench

# Host build.  Used for development and for the reference timing number.
pt21_ladder_bench: pt21_ladder_check.c pt21_ladder_check.h pt21_ladder_bench.c
	$(CC) $(CFLAGS) $(STRICT_CFLAGS) \
		pt21_ladder_check.c pt21_ladder_bench.c -o $@

# CompCert build of the checker unit.  Only `pt21_ladder_check.c` is the
# verified-compiler target; the driver keeps using the host compiler, so the
# CompCert semantic-preservation claim applies exactly to the checking code
# and to nothing else.
ccomp: pt21_ladder_bench_ccomp

pt21_ladder_check_ccomp.o: pt21_ladder_check.c pt21_ladder_check.h
	$(CCOMP) $(CCOMP_CFLAGS) -c pt21_ladder_check.c -o $@

pt21_ladder_bench_ccomp: pt21_ladder_check_ccomp.o pt21_ladder_bench.c
	$(CC) $(CFLAGS) -std=c11 pt21_ladder_bench.c \
		pt21_ladder_check_ccomp.o -o $@

test: pt21_ladder_bench
	./pt21_ladder_bench --kat

clean:
	rm -f pt21_ladder_bench pt21_ladder_bench_ccomp \
		pt21_ladder_check_ccomp.o
