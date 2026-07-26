/*
 * Copyright (c) 2026 Gershon Bialer. All rights reserved.
 * SPDX-License-Identifier: MIT
 */

/*
 * System V AMD64 trampoline for the proof-facing pure entry.
 *
 * C caller arguments:
 *   RDI entry, RSI input, RDX length, RCX result, R8 status, R9 stack_top,
 *   [caller RSP + 8] observation.
 *
 * The target receives:
 *   RDI input, RSI length, RDX result, RCX status.
 *
 * Immediately before the indirect call RSP is 0 modulo 16, so the target
 * observes RSP = 8 modulo 16 after CALL pushes this measured sentinel.
 */

    .text
    .p2align 4
    .globl tg_sq218_call_pure_entry
    .type tg_sq218_call_pure_entry,@function
tg_sq218_call_pure_entry:
    movq 8(%rsp), %r10

    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15

    movq %rsp, %r12
    movq %rdi, %r13
    movq %rsi, %r14
    movq %rdx, %r15
    movq %rcx, %rbx
    movq %r8, %rbp

    /*
     * The 32-byte restoration header occupies the top of the usable stack.
     * It is above target entry RSP and directly below the high guard page.
     * A conforming System V callee grows its own stack downward.
     */
    movq %r9, %rsp
    andq $-16, %rsp
    subq $32, %rsp
    movq %r12, 0(%rsp)
    movq %r10, 8(%rsp)

    movq $1, 0(%r10)
    leaq tg_sq218_return_sentinel(%rip), %rax
    movq %rax, 24(%r10)

    movq %r14, %rdi
    movq %r15, %rsi
    movq %rbx, %rdx
    movq %rbp, %rcx
    cld
    leaq -8(%rsp), %rax
    andq $15, %rax
    movq %rax, 32(%r10)
    call *%r13

    .globl tg_sq218_return_sentinel
    .type tg_sq218_return_sentinel,@function
tg_sq218_return_sentinel:
    movq 8(%rsp), %r10
    movl %eax, 16(%r10)
    pushfq
    popq %r11
    movq %r11, 40(%r10)
    cld
    movq $1, 8(%r10)
    movq 0(%rsp), %r12
    movq %r12, %rsp

    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
    .size tg_sq218_call_pure_entry, .-tg_sq218_call_pure_entry
    .size tg_sq218_return_sentinel, .-tg_sq218_return_sentinel

    .section .note.GNU-stack,"",@progbits
