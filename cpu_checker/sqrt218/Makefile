# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

CC ?= cc
CFLAGS ?= -O2
X86_64_CC ?= x86_64-linux-gnu-gcc
STRICT_CFLAGS := -std=c11 -Wall -Wextra -Wconversion -Werror -pedantic
PURE_ENTRY_CFLAGS := -O2 $(STRICT_CFLAGS) \
	-DTG_SQ218_PURE_ENTRY_ONLY=1 \
	-ffreestanding -fno-builtin -fno-stack-protector \
	-fno-pie -fno-asynchronous-unwind-tables -fno-unwind-tables \
	-fno-tree-loop-distribute-patterns \
	-ffunction-sections -fdata-sections
PURE_ENTRY_LDFLAGS := -nostdlib -static -no-pie \
	-Wl,--gc-sections -Wl,--build-id=none \
	-Wl,-e,tg_sq218_verify_snapshot_v2
PURE_ENTRY_SOURCES := sqrt218_cpu_checker.c sqrt218_cpu_command.c
PURE_ENTRY_HEADERS := sqrt218_cpu_checker.h sqrt218_cpu_command.h

.PHONY: all test pure-entry pure-entry-x86_64 pure-entry-host clean

all: sqrt218_cpu_checker_v2

test: sqrt218_cpu_checker_kat sqrt218_cpu_checker_v2
	./sqrt218_cpu_checker_kat

# The authority-bearing CPU route is x86-64.  This target deliberately fails
# when the pinned x86-64 cross-compiler is unavailable or has the wrong target;
# silently emitting a host-architecture image would invalidate the proof
# boundary and the Azure deployment identity.
pure-entry: pure-entry-x86_64

pure-entry-x86_64: sqrt218_cpu_checker_pure_entry_x86_64_v2

# This development-only target checks that the freestanding source closes on
# the current host.  Its artifact is never eligible for a production receipt
# and is not the subject of the x86-64 Lean refinement.
pure-entry-host: sqrt218_cpu_checker_pure_entry_host_v2

sqrt218_cpu_checker_kat: sqrt218_cpu_checker.c sqrt218_cpu_checker.h \
		sqrt218_cpu_command.c sqrt218_cpu_command.h \
		sqrt218_cpu_checker_kat.c
	$(CC) $(CFLAGS) $(STRICT_CFLAGS) \
			sqrt218_cpu_checker.c sqrt218_cpu_command.c \
			sqrt218_cpu_checker_kat.c -o $@

sqrt218_cpu_checker_v2: sqrt218_cpu_checker.c sqrt218_cpu_checker.h \
		sqrt218_cpu_command.c sqrt218_cpu_command.h \
		sqrt218_cpu_checker_cli.c
	$(CC) $(CFLAGS) $(STRICT_CFLAGS) \
			sqrt218_cpu_checker.c sqrt218_cpu_command.c \
			sqrt218_cpu_checker_cli.c -o $@

# Dedicated proof-facing artifact.  It is an x86-64 ET_EXEC image whose
# selected entry is the flat snapshot verifier, not a normal process entry
# point.  The attested launcher supplies the SysV ABI arguments directly.
# There is no libc, allocator, filesystem, syscall, dynamic loader, or startup
# code in the retained image.
sqrt218_cpu_checker_pure_entry_x86_64_v2: \
		$(PURE_ENTRY_SOURCES) $(PURE_ENTRY_HEADERS)
	@command -v "$(X86_64_CC)" >/dev/null 2>&1 || { \
		echo "missing required x86-64 compiler: $(X86_64_CC)" >&2; \
		exit 1; \
	}
	@target="$$("$(X86_64_CC)" -dumpmachine)"; \
	case "$$target" in \
		x86_64-*) ;; \
		*) echo "refusing non-x86-64 compiler target: $$target" >&2; exit 1 ;; \
	esac
	$(X86_64_CC) $(PURE_ENTRY_CFLAGS) $(PURE_ENTRY_LDFLAGS) \
			$(PURE_ENTRY_SOURCES) -o $@

sqrt218_cpu_checker_pure_entry_host_v2: \
		$(PURE_ENTRY_SOURCES) $(PURE_ENTRY_HEADERS)
	$(CC) $(PURE_ENTRY_CFLAGS) $(PURE_ENTRY_LDFLAGS) \
			$(PURE_ENTRY_SOURCES) -o $@

clean:
	rm -f sqrt218_cpu_checker_kat sqrt218_cpu_checker_v2 \
		sqrt218_cpu_checker_pure_entry_v2 \
		sqrt218_cpu_checker_pure_entry_host_v2 \
		sqrt218_cpu_checker_pure_entry_x86_64_v2
