# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.28)

project(SparkInterval LANGUAGES CXX CUDA)

find_package(CUDAToolkit REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(Threads REQUIRED)
find_path(
  SPARKINTERVAL_BOOST_INCLUDE_DIR
  boost/multiprecision/cpp_int.hpp
  DOC "Directory containing Boost.Multiprecision headers"
)
if(NOT SPARKINTERVAL_BOOST_INCLUDE_DIR)
  message(FATAL_ERROR
    "Boost.Multiprecision headers are required for the exact R2Star fallback "
    "(install libboost-dev or set SPARKINTERVAL_BOOST_INCLUDE_DIR)"
  )
endif()

option(
  SPARKINTERVAL_BUILD_H100_NATIVE
  "Build native-host H100 runners and sm_90 device artifacts"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_CDEM
  "Build the CDEM Abel full producer and independent chunk replayer"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_PROP1224
  "Build the exact Proposition 12.2.4 q-factor shard producer"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_PROP1224_MPFR
  "Build the rigorous MPFR Proposition 12.2.4 directed shard verifier"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_GOLDBACH_LADDER
  "Build the native GMP Helfgott--Platt prime-ladder producer"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_GOLDBACH_SHIFT_OR
  "Build the word-oriented Goldbach coverage kernel benchmark"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_GOLDBACH_BUCKET_SIEVE
  "Build the persistent bucketed odd-prime sieve benchmark"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_GOLDBACH_TILE_SIEVE
  "Build the race-free tile-compacted odd-prime sieve benchmark"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION
  "Build the qualification-only through-23 Goldbach word-owner wheel"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE
  "Build the production-shape Platt windowed Gamma/Taylor/phase core benchmark"
  OFF
)
option(
  SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC
  "Build the source-semantic Platt windowed transform-stage verifier"
  OFF
)
option(
  SPARKINTERVAL_ENABLE_SLOW_QUALIFICATION_TESTS
  "Register bounded source-edge CUDA qualification tests with CTest"
  OFF
)
set(
  SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD
  256
  CACHE STRING
  "Qualification-only Möbius affine rows processed per CUDA thread"
)
if(
  NOT SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD
      MATCHES "^(1|2|4|8|16|32|64|128|256|512)$"
)
  message(
    FATAL_ERROR
    "SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD must be a canonical "
    "power of two between 1 and 512"
  )
endif()
set(
  SPARKINTERVAL_HURST_MERTENS_ROOT ""
  CACHE PATH
  "Pinned greg-hurst/mertens checkout; enables the source-scale TG Mobius shard"
)
set(
  SPARKINTERVAL_PSI_PRIMESIEVE_ROOT ""
  CACHE PATH
  "Pinned kimwalisch/primesieve checkout; enables the source-scale TG psi shard"
)
set(
  SPARKINTERVAL_PSI_CRLIBM_ROOT ""
  CACHE PATH
  "Pinned CRlibm checkout providing correctly directed log for the TG psi shard"
)
set(
  SPARKINTERVAL_FLINT_PLATT_ROOT ""
  CACHE PATH
  "Pinned FLINT v3.6.0 checkout used by the Platt zeta components"
)
set(
  SPARKINTERVAL_FLINT_PLATT_PREFIX ""
  CACHE PATH
  "Install prefix of the verified FLINT v3.6.0 checkout"
)

if((SPARKINTERVAL_PSI_PRIMESIEVE_ROOT AND NOT SPARKINTERVAL_PSI_CRLIBM_ROOT)
   OR (SPARKINTERVAL_PSI_CRLIBM_ROOT AND NOT SPARKINTERVAL_PSI_PRIMESIEVE_ROOT))
  message(FATAL_ERROR
    "The TG psi shard requires both SPARKINTERVAL_PSI_PRIMESIEVE_ROOT and "
    "SPARKINTERVAL_PSI_CRLIBM_ROOT"
  )
endif()

if((SPARKINTERVAL_FLINT_PLATT_ROOT AND NOT SPARKINTERVAL_FLINT_PLATT_PREFIX)
   OR (SPARKINTERVAL_FLINT_PLATT_PREFIX AND NOT SPARKINTERVAL_FLINT_PLATT_ROOT))
  message(FATAL_ERROR
    "The Platt zeta shard requires both SPARKINTERVAL_FLINT_PLATT_ROOT and "
    "SPARKINTERVAL_FLINT_PLATT_PREFIX"
  )
endif()

if(SPARKINTERVAL_BUILD_TG_CDEM OR SPARKINTERVAL_HURST_MERTENS_ROOT)
  find_package(OpenMP REQUIRED COMPONENTS CXX)
endif()

if(SPARKINTERVAL_HURST_MERTENS_ROOT)
  execute_process(
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/tools/fetch_hurst_mertens.py"
      "${SPARKINTERVAL_HURST_MERTENS_ROOT}"
      --verify-only
    RESULT_VARIABLE SPARKINTERVAL_HURST_VERIFY_RESULT
    OUTPUT_VARIABLE SPARKINTERVAL_HURST_VERIFY_OUTPUT
    ERROR_VARIABLE SPARKINTERVAL_HURST_VERIFY_ERROR
  )
  if(NOT SPARKINTERVAL_HURST_VERIFY_RESULT EQUAL 0)
    message(FATAL_ERROR
      "The Hurst/Mertens checkout failed its pinned source-closure check:\n"
      "${SPARKINTERVAL_HURST_VERIFY_ERROR}"
    )
  endif()
endif()

if(SPARKINTERVAL_PSI_PRIMESIEVE_ROOT)
  foreach(SPARKINTERVAL_PSI_COMPONENT IN ITEMS primesieve crlibm)
    if(SPARKINTERVAL_PSI_COMPONENT STREQUAL "primesieve")
      set(SPARKINTERVAL_PSI_CHECKOUT "${SPARKINTERVAL_PSI_PRIMESIEVE_ROOT}")
    else()
      set(SPARKINTERVAL_PSI_CHECKOUT "${SPARKINTERVAL_PSI_CRLIBM_ROOT}")
    endif()
    execute_process(
      COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/fetch_psi_upstreams.py"
        "${SPARKINTERVAL_PSI_COMPONENT}"
        "${SPARKINTERVAL_PSI_CHECKOUT}"
        --verify-only
      RESULT_VARIABLE SPARKINTERVAL_PSI_VERIFY_RESULT
      OUTPUT_VARIABLE SPARKINTERVAL_PSI_VERIFY_OUTPUT
      ERROR_VARIABLE SPARKINTERVAL_PSI_VERIFY_ERROR
    )
    if(NOT SPARKINTERVAL_PSI_VERIFY_RESULT EQUAL 0)
      message(FATAL_ERROR
        "The ${SPARKINTERVAL_PSI_COMPONENT} checkout failed its pinned "
        "source-closure check:\n${SPARKINTERVAL_PSI_VERIFY_ERROR}"
      )
    endif()
  endforeach()
endif()

if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  execute_process(
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/tools/fetch_flint_platt.py"
      "${SPARKINTERVAL_FLINT_PLATT_ROOT}"
      --verify-only
    RESULT_VARIABLE SPARKINTERVAL_FLINT_PLATT_VERIFY_RESULT
    OUTPUT_VARIABLE SPARKINTERVAL_FLINT_PLATT_VERIFY_OUTPUT
    ERROR_VARIABLE SPARKINTERVAL_FLINT_PLATT_VERIFY_ERROR
  )
  if(NOT SPARKINTERVAL_FLINT_PLATT_VERIFY_RESULT EQUAL 0)
    message(FATAL_ERROR
      "The FLINT Platt checkout failed its pinned source check:\n"
      "${SPARKINTERVAL_FLINT_PLATT_VERIFY_ERROR}"
    )
  endif()
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
  set(CMAKE_CUDA_ARCHITECTURES 121)
endif()

add_library(sparkinterval_probe_kernel STATIC
  gpu/src/probe_kernel.cu
)
target_include_directories(sparkinterval_probe_kernel PUBLIC gpu/include)
set_target_properties(sparkinterval_probe_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_probe_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-probe
  gpu/src/probe_runner.cpp
)
target_include_directories(sparkinterval-probe PRIVATE gpu/include)
target_link_libraries(sparkinterval-probe PRIVATE
  sparkinterval_probe_kernel
  CUDA::cudart
)

add_library(sparkinterval_interval_batch_kernel STATIC
  gpu/src/interval_batch_kernel.cu
)
target_include_directories(sparkinterval_interval_batch_kernel PUBLIC gpu/include)
set_target_properties(sparkinterval_interval_batch_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_interval_batch_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-interval-batch
  gpu/src/interval_batch_runner.cpp
)
target_include_directories(sparkinterval-interval-batch PRIVATE gpu/include)
target_link_libraries(sparkinterval-interval-batch PRIVATE
  sparkinterval_interval_batch_kernel
  CUDA::cudart
)

add_library(sparkinterval_expression_batch_kernel STATIC
  gpu/src/expression_batch_kernel.cu
)
target_include_directories(sparkinterval_expression_batch_kernel PUBLIC gpu/include)
set_target_properties(sparkinterval_expression_batch_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_expression_batch_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-expression-batch
  gpu/src/expression_batch_runner.cpp
)
target_include_directories(sparkinterval-expression-batch PRIVATE gpu/include)
target_link_libraries(sparkinterval-expression-batch PRIVATE
  sparkinterval_expression_batch_kernel
  CUDA::cudart
)

add_executable(sparkinterval-grh-lambda
  gpu/src/grh_lambda_poc.cu
)
target_include_directories(sparkinterval-grh-lambda PRIVATE gpu/include)
set_target_properties(sparkinterval-grh-lambda PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-grh-lambda PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-grh-lambda PRIVATE CUDA::cudart)

if(SPARKINTERVAL_BUILD_TG_GOLDBACH_SHIFT_OR)
  add_executable(sparkinterval-tg-goldbach-shift-or
    gpu/platform/h100/h100_tg_goldbach_shift_or.cu
  )
  set_target_properties(sparkinterval-tg-goldbach-shift-or PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(sparkinterval-tg-goldbach-shift-or PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-goldbach-shift-or PRIVATE CUDA::cudart)
endif()

if(SPARKINTERVAL_BUILD_TG_GOLDBACH_BUCKET_SIEVE)
  add_executable(sparkinterval-tg-goldbach-bucket-sieve
    gpu/platform/h100/h100_tg_goldbach_bucket_sieve.cu
  )
  target_include_directories(sparkinterval-tg-goldbach-bucket-sieve PRIVATE
    gpu/include
  )
  set_target_properties(sparkinterval-tg-goldbach-bucket-sieve PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(sparkinterval-tg-goldbach-bucket-sieve PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-goldbach-bucket-sieve PRIVATE
    CUDA::cudart
  )
endif()

if(SPARKINTERVAL_BUILD_TG_GOLDBACH_TILE_SIEVE)
  add_executable(sparkinterval-tg-goldbach-tile-sieve
    gpu/platform/h100/h100_tg_goldbach_tile_sieve.cu
  )
  target_include_directories(sparkinterval-tg-goldbach-tile-sieve PRIVATE
    gpu/include
  )
  set_target_properties(sparkinterval-tg-goldbach-tile-sieve PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(sparkinterval-tg-goldbach-tile-sieve PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-goldbach-tile-sieve PRIVATE
    CUDA::cudart
  )
endif()

if(SPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION)
  add_executable(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification
    gpu/platform/h100/h100_tg_goldbach_word_owner_wheel23_qualification.cu
  )
  target_include_directories(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification
    PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_ENABLE_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION=1
  )
  target_compile_options(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-O3;--fmad=false;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-goldbach-word-owner-wheel23-qualification
    PRIVATE CUDA::cudart
  )
endif()

# Conditional large-q stage from Platt, arXiv:1305.3087v1, Lemma 4.2.
# This target reconstructs a Hurwitz-lattice Taylor row; it is intentionally
# not advertised as the absent CRT/Bluestein/Turing production pipeline.
add_executable(sparkinterval-tg-dirichlet-lattice
  gpu/platform/h100/h100_tg_dirichlet_lattice_kernel.cu
)
target_include_directories(sparkinterval-tg-dirichlet-lattice PRIVATE
  gpu/include
)
set_target_properties(sparkinterval-tg-dirichlet-lattice PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-lattice PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-lattice PRIVATE CUDA::cudart)

add_executable(sparkinterval-tg-dirichlet-lattice-exact
  reference/tg_dirichlet_lattice_exact.cpp
)
target_include_directories(sparkinterval-tg-dirichlet-lattice-exact PRIVATE
  gpu/include
  ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
)
target_compile_options(sparkinterval-tg-dirichlet-lattice-exact PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
)

# Compact follow-on oracle: canonical CRT unit residues are generated on the
# device and selected character coefficients are reduced without materializing
# per-residue requests or results.  This direct selected-character transform is
# not the still-missing all-character Bluestein interval FFT.
add_executable(sparkinterval-tg-dirichlet-fused
  gpu/platform/h100/h100_tg_dirichlet_fused_kernel.cu
)
target_include_directories(sparkinterval-tg-dirichlet-fused PRIVATE
  gpu/include
)
set_target_properties(sparkinterval-tg-dirichlet-fused PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-fused PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-fused PRIVATE CUDA::cudart)

add_executable(sparkinterval-tg-dirichlet-fused-exact
  reference/tg_dirichlet_fused_exact.cpp
)
target_include_directories(sparkinterval-tg-dirichlet-fused-exact PRIVATE
  gpu/include
  ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
)
target_compile_options(sparkinterval-tg-dirichlet-fused-exact PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
)

# Source-scalable realization of Platt's Lemma dc_dft.  Arbitrary cyclic
# component lengths use Bluestein plus directed radix-2 interval FFTs.  MPFR
# is used only to construct rigorous transcendental twiddle enclosures and by
# the independent CPU replay.
find_path(SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR mpfr.h REQUIRED)
find_library(SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY
  NAMES mpfr mpfr.so.6 libmpfr.so.6 REQUIRED)
find_library(SPARKINTERVAL_DIRICHLET_GMP_LIBRARY
  NAMES gmp gmp.so.10 libgmp.so.10 REQUIRED)

add_executable(sparkinterval-tg-dirichlet-chirp-recurrence-benchmark
  reference/tg_dirichlet_chirp_recurrence_benchmark.cpp
)
target_include_directories(
  sparkinterval-tg-dirichlet-chirp-recurrence-benchmark PRIVATE
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
target_compile_features(
  sparkinterval-tg-dirichlet-chirp-recurrence-benchmark PRIVATE cxx_std_20
)
target_compile_options(
  sparkinterval-tg-dirichlet-chirp-recurrence-benchmark PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-chirp-recurrence-benchmark PRIVATE
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)

if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE)
  add_executable(sparkinterval-tg-platt-gamma-stream-consumer
    reference/tg_platt_gamma_stream_consumer.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-gamma-stream-consumer PRIVATE gpu/include
  )
  target_compile_features(
    sparkinterval-tg-platt-gamma-stream-consumer PRIVATE cxx_std_20
  )
  target_compile_options(
    sparkinterval-tg-platt-gamma-stream-consumer PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
  )

  add_executable(sparkinterval-tg-platt-gamma-gpu-consumer
    gpu/platform/h100/h100_tg_platt_gamma_stream_consumer.cu
    gpu/platform/h100/tg_platt_gamma_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-gamma-gpu-consumer PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-gamma-gpu-consumer PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-gamma-gpu-consumer PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-gamma-gpu-consumer PRIVATE CUDA::cudart
  )

  add_executable(sparkinterval-tg-platt-gamma-v2-gpu-consumer
    gpu/platform/h100/h100_tg_platt_gamma_stream_v2_consumer.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-gamma-v2-gpu-consumer PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-gamma-v2-gpu-consumer PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-gamma-v2-gpu-consumer PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-gamma-v2-gpu-consumer PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(sparkinterval-tg-platt-dd-accumulator STATIC
    gpu/platform/h100/h100_tg_platt_windowed_core.cu
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-accumulator PRIVATE
    SPARKINTERVAL_PLATT_WINDOWED_CORE_NO_MAIN=1
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-accumulator PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-accumulator PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-accumulator PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-accumulator PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-tg-platt-dd-accumulator-api-smoke
    reference/tg_platt_dd_accumulator_api_smoke.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-accumulator-api-smoke PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-accumulator-api-smoke PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-accumulator-api-smoke PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-accumulator-api-smoke PRIVATE
    sparkinterval-tg-platt-dd-accumulator
  )

  add_executable(sparkinterval-tg-platt-windowed-core
    gpu/platform/h100/h100_tg_platt_windowed_core.cu
  )
  target_include_directories(sparkinterval-tg-platt-windowed-core PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(sparkinterval-tg-platt-windowed-core PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(sparkinterval-tg-platt-windowed-core PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-platt-windowed-core PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )
endif()

if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC)
  add_executable(sparkinterval-tg-platt-windowed-semantic
    gpu/platform/h100/h100_tg_platt_windowed_semantic.cu
  )
  target_include_directories(sparkinterval-tg-platt-windowed-semantic PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(sparkinterval-tg-platt-windowed-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(sparkinterval-tg-platt-windowed-semantic PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-platt-windowed-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-tg-platt-windowed-disk-semantic
    gpu/platform/h100/h100_tg_platt_windowed_disk_semantic.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-windowed-disk-semantic PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-windowed-disk-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-windowed-disk-semantic PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-windowed-disk-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-tg-platt-windowed-dd-disk-semantic
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-windowed-dd-disk-semantic PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-windowed-dd-disk-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-windowed-dd-disk-semantic PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-windowed-dd-disk-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(sparkinterval-tg-platt-dd-transform STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  target_compile_definitions(sparkinterval-tg-platt-dd-transform PRIVATE
    SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
  )
  target_include_directories(sparkinterval-tg-platt-dd-transform PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(sparkinterval-tg-platt-dd-transform PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_options(sparkinterval-tg-platt-dd-transform PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(sparkinterval-tg-platt-dd-transform PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-tg-platt-dd-transform-api-smoke
    reference/tg_platt_dd_transform_api_smoke.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-transform-api-smoke PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-transform-api-smoke PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-transform-api-smoke PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-transform-api-smoke PRIVATE
    sparkinterval-tg-platt-dd-transform
  )

  add_library(sparkinterval-tg-platt-event-scan STATIC
    gpu/platform/h100/h100_tg_platt_event_scan.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-event-scan PUBLIC gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-event-scan PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
    CUDA_RESOLVE_DEVICE_SYMBOLS ON
  )
  target_compile_options(
    sparkinterval-tg-platt-event-scan PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-event-scan PUBLIC CUDA::cudart
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-transform-api-smoke PRIVATE
    sparkinterval-tg-platt-event-scan
  )

  # Qualification-only byte-identity/performance experiment for the
  # 512-value PT21 DD FFT stages-1..9 shared-memory tile.  The default source
  # worker and its run_source_window entry point remain separate.
  add_executable(sparkinterval-tg-platt-dd-tile9-qualification
    reference/tg_platt_dd_tile9_qualification.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-tile9-qualification PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-tile9-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-tile9-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-tile9-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-tile9-qualification PRIVATE
    sparkinterval-tg-platt-dd-transform
    sparkinterval-tg-platt-event-scan
  )

  # Qualification-only comparison of the current full-expansion PT21 DD
  # root multiplication with a bounded sloppy-DD alternative.  It is
  # intentionally not linked into the transform library or source worker.
  add_executable(sparkinterval-tg-platt-dd-sloppy-mul-qualification
    reference/tg_platt_dd_sloppy_mul_qualification.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-sloppy-mul-qualification PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-sloppy-mul-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-sloppy-mul-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-sloppy-mul-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-sloppy-mul-qualification PRIVATE CUDA::cudart
  )

  # Qualification-only whole-transform build.  The ordinary production
  # transform library above is compiled without the enable macro; this
  # separate archive is the only library that contains the sloppy-root entry
  # point and it is forced to the arithmetic primitive's --fmad/--ftz
  # contract.
  add_library(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification PRIVATE
    gpu/include
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification
    PUBLIC SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-sloppy-root-transform-qualification PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    reference/tg_platt_dd_sloppy_root_whole_transform_qualification.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE gpu/include ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE
      sparkinterval-tg-platt-dd-sloppy-root-transform-qualification
      sparkinterval-tg-platt-event-scan
  )

  # Qualification-only composition of the stages-1..9 tile and the bounded
  # sloppy-root arithmetic.  This is deliberately a second archive and
  # executable: neither joint macro nor entry point reaches the production
  # transform target or the settled sloppy-root evidence binary.
  add_library(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PRIVATE
      gpu/include
      ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PUBLIC
      SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PUBLIC
      CUDA::cudart
      ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
      ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  # Qualification-only fusion of bit reversal into the stages-1..9 shared
  # tile.  Its guard and archive are distinct from both production and the
  # settled tile9 qualification, so neither existing code path can select it.
  add_library(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
    PRIVATE
      gpu/include
      ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
    PUBLIC
      SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
    PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
    PUBLIC
      CUDA::cudart
      ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
      ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    reference/tg_platt_dd_sloppy_root_whole_transform_qualification.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE gpu/include ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
  )
  target_compile_options(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE
      sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
      sparkinterval-tg-platt-event-scan
  )

  if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE)
    # Qualification-only bridge from the fully authenticated V2 Gamma stream
    # and the live exact source accumulator into the settled sloppy-root and
    # joint tile9+sloppy-root candidates.  One accumulator, transform, and
    # scanner workspace are reused sequentially; the target never changes the
    # production V2 worker's selected transform.
    add_executable(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      reference/tg_platt_pt21_live_transform_candidate_qualification.cu
      gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
    )
    target_include_directories(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      PRIVATE gpu/include ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    )
    set_target_properties(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      PROPERTIES
        CUDA_STANDARD 20
        CUDA_STANDARD_REQUIRED ON
    )
    target_compile_definitions(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      PRIVATE
        SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
        SPARKINTERVAL_CUDA_FTZ_DISABLED=1
    )
    target_compile_options(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      PRIVATE
        $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    target_link_libraries(
      sparkinterval-tg-platt-pt21-live-transform-candidate-qualification
      PRIVATE
        sparkinterval-tg-platt-dd-accumulator
        sparkinterval-tg-platt-dd-tile9-sloppy-root-transform-qualification
        sparkinterval-tg-platt-event-scan
    )

    add_executable(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      reference/tg_platt_pt21_bitreverse_tile9_qualification.cu
      gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
    )
    target_include_directories(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      PRIVATE
        gpu/include
        ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    )
    set_target_properties(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      PROPERTIES
        CUDA_STANDARD 20
        CUDA_STANDARD_REQUIRED ON
    )
    target_compile_definitions(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      PRIVATE
        SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
        SPARKINTERVAL_CUDA_FTZ_DISABLED=1
    )
    target_compile_options(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      PRIVATE
        $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    target_link_libraries(
      sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification
      PRIVATE
        sparkinterval-tg-platt-dd-accumulator
        sparkinterval-tg-platt-dd-bitreverse-tile9-transform-qualification
        sparkinterval-tg-platt-event-scan
    )
  endif()

  add_executable(sparkinterval-tg-platt-event-scan-benchmark
    reference/tg_platt_event_scan_benchmark.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-event-scan-benchmark PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-event-scan-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-event-scan-benchmark PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
  )
  target_compile_options(
    sparkinterval-tg-platt-event-scan-benchmark PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-event-scan-benchmark PRIVATE
    sparkinterval-tg-platt-event-scan
  )

  add_executable(sparkinterval-tg-platt-event-record-kat
    reference/tg_platt_event_record_kat.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-event-record-kat PRIVATE gpu/include
  )
  target_compile_features(
    sparkinterval-tg-platt-event-record-kat PRIVATE cxx_std_20
  )
  target_compile_options(
    sparkinterval-tg-platt-event-record-kat PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
  )
endif()

if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE AND
   SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC)
  add_executable(sparkinterval-tg-platt-fused-source-worker
    gpu/platform/h100/h100_tg_platt_fused_source_worker.cu
    gpu/platform/h100/tg_platt_gamma_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-fused-source-worker PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-fused-source-worker PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_options(
    sparkinterval-tg-platt-fused-source-worker PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-fused-source-worker PRIVATE
    sparkinterval-tg-platt-dd-accumulator
    sparkinterval-tg-platt-dd-transform
  )

  add_executable(sparkinterval-tg-platt-fused-source-worker-v2
    gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-fused-source-worker-v2 PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-fused-source-worker-v2 PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-fused-source-worker-v2 PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
  )
  target_compile_options(
    sparkinterval-tg-platt-fused-source-worker-v2 PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-fused-source-worker-v2 PRIVATE
    sparkinterval-tg-platt-dd-accumulator
    sparkinterval-tg-platt-dd-transform
    sparkinterval-tg-platt-event-scan
    Threads::Threads
  )

  # Qualification-only producer/consumer overlap for ordinary, independently
  # centered PT21 windows.  The production V2 worker is intentionally
  # unchanged; this target compares all samples and scanner artifacts with a
  # separate sequential execution.
  add_executable(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification
    reference/tg_platt_pt21_recentered_pipeline_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification
    PRIVATE gpu/include
  )
  set_target_properties(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
  )
  target_compile_options(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-pt21-recentered-pipeline-qualification PRIVATE
    sparkinterval-tg-platt-dd-accumulator
    sparkinterval-tg-platt-dd-transform
    sparkinterval-tg-platt-event-scan
  )

  # Qualification-only exact lattice-window reuse experiment.  This target
  # is deliberately separate from the default V2 worker and emits no source
  # or production certificate.
  if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  add_executable(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification
    reference/tg_platt_pt21_multiwindow_reuse_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  target_include_directories(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification
    PRIVATE gpu/include ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
  )
  target_compile_options(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  target_link_libraries(
    sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification PRIVATE
    sparkinterval-tg-platt-dd-accumulator
    sparkinterval-tg-platt-dd-transform
    sparkinterval-tg-platt-event-scan
    sparkinterval-tg-platt-stationary-junction
  )
  endif()
endif()

add_executable(sparkinterval-tg-dirichlet-allchars
  gpu/platform/h100/h100_tg_dirichlet_allchars_bluestein.cu
)
target_include_directories(sparkinterval-tg-dirichlet-allchars PRIVATE
  gpu/include
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
set_target_properties(sparkinterval-tg-dirichlet-allchars PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-allchars PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-allchars PRIVATE
  CUDA::cudart
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)

# Small deterministic resident allchars/completed-L handoff fixture.  This is
# deliberately separate from the full Python allchars KAT so every CUDA tool
# can inspect the exact transform-to-reducer seam directly.
set(
  SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR
  "${CMAKE_CURRENT_BINARY_DIR}/tg-dirichlet-resident-handoff-fixture"
)
set(
  SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_TOOL
  "${CMAKE_CURRENT_SOURCE_DIR}/tools/tg_dirichlet_resident_handoff_fixture.py"
)
add_custom_command(
  OUTPUT
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/fixture.json"
  BYPRODUCTS
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/input.bin"
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/roots.bin"
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/factors.bin"
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/completed-factor-recurrence/gamma.bin"
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/completed-factor-recurrence/steps.bin"
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/completed-factor-recurrence/checkpoints.bin"
  COMMAND
    ${Python3_EXECUTABLE}
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_TOOL}"
    prepare
    --directory
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}"
  DEPENDS
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_TOOL}"
    "${CMAKE_CURRENT_SOURCE_DIR}/tg_verifier/dirichlet_resident_handoff_fixture.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tg_verifier/dirichlet_completed_factor_artifacts.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tg_verifier/dirichlet_allchars_stage.py"
  COMMENT "Preparing the bounded resident allchars/completed-L fixture"
  VERBATIM
)
add_custom_target(
  sparkinterval-tg-dirichlet-resident-handoff-fixture
  DEPENDS
    "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/fixture.json"
)
add_dependencies(
  sparkinterval-tg-dirichlet-resident-handoff-fixture
  sparkinterval-tg-dirichlet-allchars
)

find_program(
  SPARKINTERVAL_COMPUTE_SANITIZER
  NAMES compute-sanitizer
  HINTS "${CUDAToolkit_BIN_DIR}"
)
if(SPARKINTERVAL_COMPUTE_SANITIZER)
  foreach(
    SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TOOL
    IN ITEMS memcheck initcheck racecheck synccheck
  )
    set(
      SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TARGET
      "sparkinterval-tg-dirichlet-resident-handoff-${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TOOL}"
    )
    add_custom_target(
      "${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TARGET}"
      COMMAND
        ${Python3_EXECUTABLE}
        "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_TOOL}"
        run
        --directory
        "${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TOOL}"
        --runner
        $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
        --device 0
        --compute-sanitizer
        "${SPARKINTERVAL_COMPUTE_SANITIZER}"
        --sanitizer-tool
        "${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TOOL}"
      COMMENT
        "Running resident allchars/completed-L ${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TOOL}"
      USES_TERMINAL
      VERBATIM
    )
    add_dependencies(
      "${SPARKINTERVAL_TG_DIRICHLET_SANITIZER_TARGET}"
      sparkinterval-tg-dirichlet-allchars
    )
  endforeach()
endif()

add_executable(sparkinterval-tg-dirichlet-allchars-mpfr
  reference/tg_dirichlet_allchars_mpfr.cpp
)
target_include_directories(sparkinterval-tg-dirichlet-allchars-mpfr PRIVATE
  gpu/include
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
target_link_libraries(sparkinterval-tg-dirichlet-allchars-mpfr PRIVATE
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)
target_compile_options(sparkinterval-tg-dirichlet-allchars-mpfr PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
)

add_custom_target(
  sparkinterval-tg-dirichlet-allchars-max-order-impulse-qualification
  COMMAND
    ${Python3_EXECUTABLE}
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_impulse_qualification.py
    --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
    --device 0
    --maximum-seconds 300
  DEPENDS
    sparkinterval-tg-dirichlet-allchars
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_impulse_qualification.py
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Qualifying the maximum-order 2^20 CUDA Bluestein dataflow"
  USES_TERMINAL
  VERBATIM
)

add_custom_target(
  sparkinterval-tg-dirichlet-allchars-max-order-delta-one-qualification
  COMMAND
    ${Python3_EXECUTABLE}
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_delta_one_qualification.py
    --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
    --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
    --device 0
    --maximum-seconds 300
    --checker-timeout 120
  DEPENDS
    sparkinterval-tg-dirichlet-allchars
    sparkinterval-tg-dirichlet-allchars-mpfr
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_delta_one_qualification.py
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Qualifying the maximum-order delta-one DFT against direct MPFR"
  USES_TERMINAL
  VERBATIM
)

add_custom_target(
  sparkinterval-tg-dirichlet-fft-root-recurrence-qualification
  COMMAND
    ${Python3_EXECUTABLE}
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_fft_root_recurrence_qualification.py
    --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
    --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
    --command-timeout 120
  DEPENDS
    sparkinterval-tg-dirichlet-allchars
    sparkinterval-tg-dirichlet-allchars-mpfr
    ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_fft_root_recurrence_qualification.py
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Qualifying every production radix-2 FFT-root recurrence table"
  USES_TERMINAL
  VERBATIM
)

# Independent MPFR replay for the bounded adapter that combines certified
# Hurwitz Taylor rows, finite recovery terms, and q^(-1/2-it) before the
# all-character transform.  This checker deliberately does not share the
# Python adapter's interval operators or CRT reconstruction.
add_executable(sparkinterval-tg-dirichlet-residue-composition-mpfr
  reference/tg_dirichlet_residue_composition_mpfr.cpp
)
target_include_directories(
  sparkinterval-tg-dirichlet-residue-composition-mpfr PRIVATE
  gpu/include
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
target_link_libraries(
  sparkinterval-tg-dirichlet-residue-composition-mpfr PRIVATE
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)
target_compile_options(
  sparkinterval-tg-dirichlet-residue-composition-mpfr PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
)

# Fused large-q directed-box stage.  One persistent process and one CUDA
# kernel handle up to 64 ordinates for a fixed q, performing Taylor
# reconstruction and residue composition without device transcendental calls.
add_executable(sparkinterval-tg-dirichlet-largeq-batch
  gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu
)
target_include_directories(sparkinterval-tg-dirichlet-largeq-batch PRIVATE
  gpu/include
)
set_target_properties(sparkinterval-tg-dirichlet-largeq-batch PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-largeq-batch PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-largeq-batch PRIVATE
  CUDA::cudart
)

# Seeded large-q frontend.  Its --tmajor-block mode consumes the authenticated
# one-copy-per-row TGDLTMB1 artifact, uploads each lattice block once, derives
# canonical descriptors on the worker, and streams ordinary TGDAFFI1 frames.
# Its bounded --formulaic-qmajor-service mode consumes a compact q-major
# cursor stream with no descriptor or per-target JSON roster, caching the
# reconstructed descriptor table across consecutive targets for the same q.
# Its bounded --resident-qmajor-phase mode authenticates one contiguous
# t-row shard, uploads it once, reconstructs active/clipped q targets from the
# schedule, and executes them in canonical q-major order.
# The Python builder either converts fully authenticated q-major KAT inputs or
# directly generates higher-precision-replayed MPFR factors and exact tails.
add_executable(sparkinterval-tg-dirichlet-largeq-seeded
  gpu/platform/h100/h100_tg_dirichlet_largeq_seeded_batch.cu
)
target_include_directories(sparkinterval-tg-dirichlet-largeq-seeded PRIVATE
  gpu/include
)
set_target_properties(sparkinterval-tg-dirichlet-largeq-seeded PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-largeq-seeded PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-largeq-seeded PRIVATE
  CUDA::cudart
)

# Source-shaped resident q-major phase executor.  Rows and bounded q/lane
# sidecars remain separate immutable streams; the worker incrementally uploads
# rows into one preallocated resident device buffer and emits TGDAFFI1 targets.
add_executable(sparkinterval-tg-dirichlet-resident-qmajor-stream
  gpu/platform/h100/h100_tg_dirichlet_resident_qmajor_stream.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-resident-qmajor-stream PRIVATE
  gpu/include
)
set_target_properties(
  sparkinterval-tg-dirichlet-resident-qmajor-stream PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-resident-qmajor-stream PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-resident-qmajor-stream PRIVATE
  CUDA::cudart
)

# Platt's small-conductor Booker/Gaussian finite-sum accelerator. CUDA output
# is an explicitly untrusted proposal: the Python Arb path supplies analytic
# tails and retained interval replay, while the C++ MPFR program is a separate
# arithmetic audit.
add_executable(sparkinterval-tg-dirichlet-booker-smallq
  gpu/platform/h100/h100_tg_dirichlet_booker_smallq_kernel.cu
)
target_include_directories(sparkinterval-tg-dirichlet-booker-smallq PRIVATE
  gpu/include
)
set_target_properties(sparkinterval-tg-dirichlet-booker-smallq PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(sparkinterval-tg-dirichlet-booker-smallq PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(sparkinterval-tg-dirichlet-booker-smallq PRIVATE
  CUDA::cudart
)

add_executable(sparkinterval-tg-dirichlet-booker-smallq-mpfr
  reference/tg_dirichlet_booker_smallq.cpp
)
target_include_directories(
  sparkinterval-tg-dirichlet-booker-smallq-mpfr PRIVATE
  gpu/include
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
target_link_libraries(sparkinterval-tg-dirichlet-booker-smallq-mpfr PRIVATE
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)
target_compile_options(sparkinterval-tg-dirichlet-booker-smallq-mpfr PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Wpedantic;-Werror>
)

# Version 2 replaces the midpoint proposal with directed complex disks;
# version 3 additionally factors the character epsilon from the parity-only
# frequency seed.  Both formats are independently regenerated by the Python
# Arb checker.  CUDA evaluates basic directed arithmetic, square roots, the
# finite Gaussian recurrence, and a persistent radix-2 DFT.
add_executable(sparkinterval-tg-dirichlet-booker-smallq-certified
  gpu/platform/h100/h100_tg_dirichlet_booker_smallq_certified.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-booker-smallq-certified PRIVATE
  gpu/include
  ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
)
set_target_properties(
  sparkinterval-tg-dirichlet-booker-smallq-certified PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-booker-smallq-certified PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-booker-smallq-certified PRIVATE
  CUDA::cudart
  ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
  ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
)

add_executable(sparkinterval-tg-dirichlet-strict-sign-pack-kat
  tests/tg_dirichlet_strict_sign_pack_known_answers.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-strict-sign-pack-kat PRIVATE gpu/include
)
set_target_properties(
  sparkinterval-tg-dirichlet-strict-sign-pack-kat PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-strict-sign-pack-kat PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-strict-sign-pack-kat PRIVATE CUDA::cudart
)

add_executable(sparkinterval-tg-dirichlet-completed-sign-reducer-kat
  tests/tg_dirichlet_completed_sign_reducer_known_answers.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-completed-sign-reducer-kat PRIVATE gpu/include
)
set_target_properties(
  sparkinterval-tg-dirichlet-completed-sign-reducer-kat PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-completed-sign-reducer-kat PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-completed-sign-reducer-kat PRIVATE CUDA::cudart
)

add_executable(sparkinterval-tg-dirichlet-resident-phase-accumulator-kat
  tests/tg_dirichlet_resident_phase_accumulator_known_answers.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-resident-phase-accumulator-kat PRIVATE
  gpu/include
)
set_target_properties(
  sparkinterval-tg-dirichlet-resident-phase-accumulator-kat PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-resident-phase-accumulator-kat PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-resident-phase-accumulator-kat PRIVATE
  CUDA::cudart
)

add_executable(sparkinterval-tg-dirichlet-factor8-postprocess
  gpu/platform/h100/h100_tg_dirichlet_factor8_postprocess.cu
)
target_include_directories(
  sparkinterval-tg-dirichlet-factor8-postprocess PRIVATE gpu/include
)
set_target_properties(
  sparkinterval-tg-dirichlet-factor8-postprocess PROPERTIES
  CUDA_STANDARD 20
  CUDA_STANDARD_REQUIRED ON
)
target_compile_options(
  sparkinterval-tg-dirichlet-factor8-postprocess PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)
target_link_libraries(
  sparkinterval-tg-dirichlet-factor8-postprocess PRIVATE CUDA::cudart
)

if(SPARKINTERVAL_BUILD_H100_NATIVE)
  if(CMAKE_CUDA_COMPILER_VERSION VERSION_LESS 11.8)
    message(FATAL_ERROR
      "H100 native targets require CUDA 11.8 or newer for sm_90 support"
    )
  endif()

  find_program(
    SPARKINTERVAL_CUOBJDUMP
    NAMES cuobjdump
    HINTS
      "${CUDAToolkit_BIN_DIR}"
      "${CMAKE_CUDA_COMPILER_TOOLKIT_ROOT}/bin"
    REQUIRED
  )

  set(SPARKINTERVAL_H100_PROBE_CUBIN_DIR
      "${CMAKE_CURRENT_BINARY_DIR}/h100")
  set(SPARKINTERVAL_H100_PROBE_CUBIN
      "${SPARKINTERVAL_H100_PROBE_CUBIN_DIR}/h100_rounding_probe.sm_90.cubin")

  add_custom_command(
    OUTPUT "${SPARKINTERVAL_H100_PROBE_CUBIN}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory
            "${SPARKINTERVAL_H100_PROBE_CUBIN_DIR}"
    COMMAND "${CMAKE_CUDA_COMPILER}"
            -std=c++17
            --cubin
            --gpu-architecture=compute_90
            --gpu-code=sm_90
            --fmad=false
            --ftz=false
            --prec-div=true
            --prec-sqrt=true
            --generate-line-info
            "${CMAKE_CURRENT_SOURCE_DIR}/gpu/platform/h100/h100_rounding_probe.cu"
            --output-file "${SPARKINTERVAL_H100_PROBE_CUBIN}"
    DEPENDS gpu/platform/h100/h100_rounding_probe.cu
    COMMENT "Building the fixed H100 directed-rounding probe cubin"
    VERBATIM
  )
  add_custom_target(sparkinterval-h100-probe-cubin ALL
    DEPENDS "${SPARKINTERVAL_H100_PROBE_CUBIN}"
  )

  add_executable(sparkinterval-h100-probe-runner
    gpu/platform/h100/h100_probe_runner.cpp
  )
  target_link_libraries(sparkinterval-h100-probe-runner PRIVATE
    CUDA::cuda_driver
  )
  target_compile_options(sparkinterval-h100-probe-runner PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
  )

  function(sparkinterval_configure_h100_kernel target)
    target_include_directories(${target} PUBLIC gpu/include)
    set_target_properties(${target} PROPERTIES
      CUDA_ARCHITECTURES 90
      CUDA_STANDARD 17
      CUDA_STANDARD_REQUIRED ON
      POSITION_INDEPENDENT_CODE ON
    )
    target_compile_options(${target} PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
  endfunction()

  add_library(sparkinterval_h100_interval_batch_kernel STATIC
    gpu/platform/h100/h100_interval_batch_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_interval_batch_kernel
  )

  add_executable(sparkinterval-h100-interval-batch
    gpu/platform/h100/h100_interval_batch_runner.cpp
  )
  target_include_directories(sparkinterval-h100-interval-batch PRIVATE
    gpu/include
  )
  target_link_libraries(sparkinterval-h100-interval-batch PRIVATE
    sparkinterval_h100_interval_batch_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-interval-batch PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
  )

  add_library(sparkinterval_h100_expression_batch_kernel STATIC
    gpu/platform/h100/h100_expression_batch_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_expression_batch_kernel
  )

  add_executable(sparkinterval-h100-expression-batch
    gpu/platform/h100/h100_expression_batch_runner.cpp
  )
  target_include_directories(sparkinterval-h100-expression-batch PRIVATE
    gpu/include
  )
  target_link_libraries(sparkinterval-h100-expression-batch PRIVATE
    sparkinterval_h100_expression_batch_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-expression-batch PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
  )

  # The upstream GRH interval evaluator is also built as an explicitly
  # H100-bound sm_90 executable.  It remains the moderate-height POC
  # algorithm; this target binding does not make it a Platt-scale backend.
  add_executable(sparkinterval-h100-grh-lambda
    gpu/src/grh_lambda_poc.cu
  )
  sparkinterval_configure_h100_kernel(sparkinterval-h100-grh-lambda)
  target_compile_definitions(sparkinterval-h100-grh-lambda PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(sparkinterval-h100-grh-lambda PRIVATE CUDA::cudart)

  add_executable(sparkinterval-h100-tg-dirichlet-lattice
    gpu/platform/h100/h100_tg_dirichlet_lattice_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-lattice
  )
  set_target_properties(sparkinterval-h100-tg-dirichlet-lattice PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(sparkinterval-h100-tg-dirichlet-lattice PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(sparkinterval-h100-tg-dirichlet-lattice PRIVATE
    CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-dirichlet-fused
    gpu/platform/h100/h100_tg_dirichlet_fused_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-fused
  )
  set_target_properties(sparkinterval-h100-tg-dirichlet-fused PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(sparkinterval-h100-tg-dirichlet-fused PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(sparkinterval-h100-tg-dirichlet-fused PRIVATE
    CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-dirichlet-allchars
    gpu/platform/h100/h100_tg_dirichlet_allchars_bluestein.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-allchars
  )
  target_include_directories(sparkinterval-h100-tg-dirichlet-allchars PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(sparkinterval-h100-tg-dirichlet-allchars PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(sparkinterval-h100-tg-dirichlet-allchars PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(sparkinterval-h100-tg-dirichlet-allchars PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-platt-windowed-core
    gpu/platform/h100/h100_tg_platt_windowed_core.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-windowed-core
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-windowed-core PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(sparkinterval-h100-tg-platt-windowed-core PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-windowed-core PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(sparkinterval-h100-tg-platt-windowed-core PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-platt-gamma-gpu-consumer
    gpu/platform/h100/h100_tg_platt_gamma_stream_consumer.cu
    gpu/platform/h100/tg_platt_gamma_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-gamma-gpu-consumer
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-gamma-gpu-consumer PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-gamma-gpu-consumer PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-gamma-gpu-consumer PRIVATE CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer
    gpu/platform/h100/h100_tg_platt_gamma_stream_v2_consumer.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-gamma-v2-gpu-consumer PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-platt-windowed-semantic
    gpu/platform/h100/h100_tg_platt_windowed_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-windowed-semantic
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-windowed-semantic PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-windowed-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-windowed-semantic PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-windowed-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-platt-windowed-disk-semantic
    gpu/platform/h100/h100_tg_platt_windowed_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-windowed-disk-semantic
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-windowed-disk-semantic PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-windowed-disk-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-windowed-disk-semantic PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-windowed-disk-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-platt-windowed-dd-disk-semantic
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-windowed-dd-disk-semantic
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-windowed-dd-disk-semantic PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-windowed-dd-disk-semantic PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-windowed-dd-disk-semantic PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-windowed-dd-disk-semantic PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(sparkinterval-h100-tg-platt-dd-accumulator STATIC
    gpu/platform/h100/h100_tg_platt_windowed_core.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-accumulator
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-accumulator PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-accumulator PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-accumulator PRIVATE
    SPARKINTERVAL_PLATT_WINDOWED_CORE_NO_MAIN=1
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-accumulator PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(sparkinterval-h100-tg-platt-dd-transform STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-transform
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-transform PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-transform PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-transform PRIVATE
    SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-transform PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(sparkinterval-h100-tg-platt-event-scan STATIC
    gpu/platform/h100/h100_tg_platt_event_scan.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-event-scan
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-event-scan PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_SEPARABLE_COMPILATION ON
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-event-scan PUBLIC CUDA::cudart
  )

  # Strict H100 counterpart to the qualification-only stages-1..9 DD tile.
  # It links only the sm_90 transform/scanner libraries and rejects every
  # non-H100 device before running a qualification case.
  add_executable(sparkinterval-h100-tg-platt-dd-tile9-qualification
    reference/tg_platt_dd_tile9_qualification.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-tile9-qualification
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-tile9-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-tile9-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-tile9-qualification PRIVATE
    sparkinterval-h100-tg-platt-dd-transform
    sparkinterval-h100-tg-platt-event-scan
  )

  add_executable(sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification
    reference/tg_platt_dd_sloppy_mul_qualification.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification PRIVATE
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_CUDA_FTZ_DISABLED=1
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-sloppy-mul-qualification PRIVATE
    CUDA::cudart
  )

  add_library(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification
    PUBLIC SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification PUBLIC
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
    reference/tg_platt_dd_sloppy_root_whole_transform_qualification.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-sloppy-root-whole-transform-qualification
    PRIVATE
      sparkinterval-h100-tg-platt-dd-sloppy-root-transform-qualification
      sparkinterval-h100-tg-platt-event-scan
  )

  add_library(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
    STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PRIVATE ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PUBLIC
      SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
    PUBLIC
      CUDA::cudart
      ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
      ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_library(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
    STATIC
    gpu/platform/h100/h100_tg_platt_windowed_dd_disk_semantic.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
    PRIVATE ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
    PUBLIC
      SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_TILE9_SLOPPY_ROOT_QUALIFICATION=1
      SPARKINTERVAL_ENABLE_BITREVERSE_TILE9_QUALIFICATION=1
    PRIVATE
      SPARKINTERVAL_PLATT_DD_DISK_NO_MAIN=1
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
    PUBLIC
      CUDA::cudart
      ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
      ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    reference/tg_platt_dd_sloppy_root_whole_transform_qualification.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification
    PRIVATE
      sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
      sparkinterval-h100-tg-platt-event-scan
  )

  add_executable(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
    reference/tg_platt_pt21_live_transform_candidate_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
    PRIVATE ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-pt21-live-transform-candidate-qualification
    PRIVATE
      sparkinterval-h100-tg-platt-dd-accumulator
      sparkinterval-h100-tg-platt-dd-tile9-sloppy-root-transform-qualification
      sparkinterval-h100-tg-platt-event-scan
  )

  add_executable(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
    reference/tg_platt_pt21_bitreverse_tile9_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
    PRIVATE ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
    PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
    PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_CUDA_FTZ_DISABLED=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-pt21-bitreverse-tile9-qualification
    PRIVATE
      sparkinterval-h100-tg-platt-dd-accumulator
      sparkinterval-h100-tg-platt-dd-bitreverse-tile9-transform-qualification
      sparkinterval-h100-tg-platt-event-scan
  )

  add_executable(sparkinterval-h100-tg-platt-fused-source-worker
    gpu/platform/h100/h100_tg_platt_fused_source_worker.cu
    gpu/platform/h100/tg_platt_gamma_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-fused-source-worker
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-fused-source-worker PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-fused-source-worker PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-fused-source-worker PRIVATE
    sparkinterval-h100-tg-platt-dd-accumulator
    sparkinterval-h100-tg-platt-dd-transform
  )

  add_executable(sparkinterval-h100-tg-platt-fused-source-worker-v2
    gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-fused-source-worker-v2
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-fused-source-worker-v2 PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-fused-source-worker-v2 PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-fused-source-worker-v2 PRIVATE
    sparkinterval-h100-tg-platt-dd-accumulator
    sparkinterval-h100-tg-platt-dd-transform
    sparkinterval-h100-tg-platt-event-scan
    Threads::Threads
  )

  add_executable(
    sparkinterval-h100-tg-platt-pt21-recentered-pipeline-qualification
    reference/tg_platt_pt21_recentered_pipeline_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-pt21-recentered-pipeline-qualification
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-pt21-recentered-pipeline-qualification
    PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-pt21-recentered-pipeline-qualification
    PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-pt21-recentered-pipeline-qualification
    PRIVATE
    sparkinterval-h100-tg-platt-dd-accumulator
    sparkinterval-h100-tg-platt-dd-transform
    sparkinterval-h100-tg-platt-event-scan
  )

  if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  add_executable(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
    reference/tg_platt_pt21_multiwindow_reuse_qualification.cu
    gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
  )
  target_include_directories(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
    PRIVATE ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
    PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification
    PRIVATE
    SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-platt-pt21-multiwindow-reuse-qualification PRIVATE
    sparkinterval-h100-tg-platt-dd-accumulator
    sparkinterval-h100-tg-platt-dd-transform
    sparkinterval-h100-tg-platt-event-scan
    sparkinterval-h100-tg-platt-stationary-junction
  )
  endif()

  add_executable(sparkinterval-h100-tg-dirichlet-largeq-batch
    gpu/platform/h100/h100_tg_dirichlet_largeq_batch.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-largeq-batch
  )
  set_target_properties(
    sparkinterval-h100-tg-dirichlet-largeq-batch PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-dirichlet-largeq-batch PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-dirichlet-largeq-batch PRIVATE CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-dirichlet-largeq-seeded
    gpu/platform/h100/h100_tg_dirichlet_largeq_seeded_batch.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-largeq-seeded
  )
  set_target_properties(
    sparkinterval-h100-tg-dirichlet-largeq-seeded PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-dirichlet-largeq-seeded PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-dirichlet-largeq-seeded PRIVATE CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-dirichlet-booker-smallq
    gpu/platform/h100/h100_tg_dirichlet_booker_smallq_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-booker-smallq
  )
  set_target_properties(
    sparkinterval-h100-tg-dirichlet-booker-smallq PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-dirichlet-booker-smallq PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-dirichlet-booker-smallq PRIVATE CUDA::cudart
  )

  add_executable(sparkinterval-h100-tg-dirichlet-booker-smallq-certified
    gpu/platform/h100/h100_tg_dirichlet_booker_smallq_certified.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified
  )
  target_include_directories(
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified PRIVATE
    ${SPARKINTERVAL_DIRICHLET_MPFR_INCLUDE_DIR}
  )
  set_target_properties(
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified PRIVATE
    CUDA::cudart
    ${SPARKINTERVAL_DIRICHLET_MPFR_LIBRARY}
    ${SPARKINTERVAL_DIRICHLET_GMP_LIBRARY}
  )

  add_executable(sparkinterval-h100-tg-dirichlet-factor8-postprocess
    gpu/platform/h100/h100_tg_dirichlet_factor8_postprocess.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval-h100-tg-dirichlet-factor8-postprocess
  )
  set_target_properties(
    sparkinterval-h100-tg-dirichlet-factor8-postprocess PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
  )
  target_compile_definitions(
    sparkinterval-h100-tg-dirichlet-factor8-postprocess PRIVATE
    SPARKINTERVAL_REQUIRE_H100_SM90=1
  )
  target_link_libraries(
    sparkinterval-h100-tg-dirichlet-factor8-postprocess PRIVATE CUDA::cudart
  )

  add_library(sparkinterval_h100_tg_r2star_factor_support_kernel STATIC
    gpu/platform/h100/h100_tg_r2star_factor_support_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_tg_r2star_factor_support_kernel
  )

  add_executable(sparkinterval-h100-tg-r2star-factor-support
    gpu/platform/h100/h100_tg_r2star_factor_support_runner.cpp
  )
  target_include_directories(
    sparkinterval-h100-tg-r2star-factor-support PRIVATE gpu/include
  )
  target_link_libraries(sparkinterval-h100-tg-r2star-factor-support PRIVATE
    sparkinterval_h100_tg_r2star_factor_support_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-tg-r2star-factor-support PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
  )

  add_library(sparkinterval_h100_tg_r2star_chunk_kernel STATIC
    gpu/platform/h100/h100_tg_r2star_chunk_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_tg_r2star_chunk_kernel
  )

  add_executable(sparkinterval-h100-tg-r2star-chunk
    gpu/platform/h100/h100_tg_r2star_chunk_runner.cpp
  )
  target_include_directories(sparkinterval-h100-tg-r2star-chunk PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
  )
  target_link_libraries(sparkinterval-h100-tg-r2star-chunk PRIVATE
    sparkinterval_h100_tg_r2star_factor_support_kernel
    sparkinterval_h100_tg_r2star_chunk_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-tg-r2star-chunk PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
  )

  add_library(sparkinterval_h100_tg_mobius_segment_kernel STATIC
    gpu/platform/h100/h100_tg_mobius_segment_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_tg_mobius_segment_kernel
  )
  target_compile_definitions(
    sparkinterval_h100_tg_mobius_segment_kernel
    PUBLIC
      SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD=${SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD}
  )

  add_executable(sparkinterval-h100-tg-mobius-segment
    gpu/platform/h100/h100_tg_mobius_segment_runner.cpp
  )
  target_include_directories(
    sparkinterval-h100-tg-mobius-segment PRIVATE gpu/include
  )
  target_link_libraries(sparkinterval-h100-tg-mobius-segment PRIVATE
    sparkinterval_h100_tg_mobius_segment_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-tg-mobius-segment PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
  )

  add_executable(sparkinterval-h100-tg-mobius-persistent
    gpu/platform/h100/h100_tg_mobius_persistent_runner.cpp
  )
  target_include_directories(
    sparkinterval-h100-tg-mobius-persistent PRIVATE gpu/include
  )
  target_link_libraries(sparkinterval-h100-tg-mobius-persistent PRIVATE
    sparkinterval_h100_tg_mobius_segment_kernel
    CUDA::cudart
  )
  target_compile_options(sparkinterval-h100-tg-mobius-persistent PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
  )

  add_executable(sparkinterval-h100-runtime-policy-known-answers
    tests/h100_runtime_policy_known_answers.cpp
  )
  target_include_directories(
    sparkinterval-h100-runtime-policy-known-answers
    PRIVATE gpu/include gpu/platform/h100
  )
  target_link_libraries(
    sparkinterval-h100-runtime-policy-known-answers PRIVATE CUDA::cudart
  )
  target_compile_options(
    sparkinterval-h100-runtime-policy-known-answers PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
  )

  add_library(sparkinterval_h100_tg_prop1224_factor_kernel STATIC
    gpu/platform/h100/h100_tg_prop1224_factor_kernel.cu
  )
  sparkinterval_configure_h100_kernel(
    sparkinterval_h100_tg_prop1224_factor_kernel
  )

  if(SPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION)
    add_executable(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification
      gpu/platform/h100/h100_tg_goldbach_word_owner_wheel23_qualification.cu
    )
    sparkinterval_configure_h100_kernel(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification
    )
    set_target_properties(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification
      PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
    )
    target_compile_definitions(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_ENABLE_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION=1
      SPARKINTERVAL_REQUIRE_H100_SM90=1
    )
    target_compile_options(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:-O3>
    )
    target_link_libraries(
      sparkinterval-h100-tg-goldbach-word-owner-wheel23-qualification
      PRIVATE CUDA::cudart
    )
  endif()

  add_custom_target(sparkinterval-h100-native)
  add_dependencies(sparkinterval-h100-native
    sparkinterval-h100-probe-cubin
    sparkinterval-h100-probe-runner
    sparkinterval-h100-interval-batch
    sparkinterval-h100-expression-batch
    sparkinterval-h100-grh-lambda
    sparkinterval-h100-tg-r2star-factor-support
    sparkinterval-h100-tg-r2star-chunk
    sparkinterval-h100-tg-mobius-segment
    sparkinterval-h100-tg-mobius-persistent
    sparkinterval-h100-runtime-policy-known-answers
    sparkinterval-h100-tg-dirichlet-lattice
    sparkinterval-h100-tg-dirichlet-fused
    sparkinterval-h100-tg-dirichlet-allchars
    sparkinterval-h100-tg-dirichlet-largeq-batch
    sparkinterval-h100-tg-dirichlet-booker-smallq
    sparkinterval-h100-tg-dirichlet-booker-smallq-certified
    sparkinterval-h100-tg-dirichlet-factor8-postprocess
    sparkinterval_h100_tg_prop1224_factor_kernel
  )
endif()

add_executable(sparkinterval-generated-driver
  gpu/src/generated_ptx_driver.cpp
)
target_include_directories(sparkinterval-generated-driver PRIVATE gpu/include)
target_link_libraries(sparkinterval-generated-driver PRIVATE CUDA::cuda_driver)

add_library(sparkinterval_tg_workload_benchmark_kernel STATIC
  gpu/src/tg_workload_benchmark_kernel.cu
)
target_include_directories(sparkinterval_tg_workload_benchmark_kernel PUBLIC gpu/include)
set_target_properties(sparkinterval_tg_workload_benchmark_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_tg_workload_benchmark_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-tg-workload-benchmark
  gpu/src/tg_workload_benchmark_runner.cpp
)

# Production-scale streaming finalizer for the optimized PT21 block/shard
# commitment chain.  It has no FLINT dependency: the validated adapter (or a
# future complete measured H100 worker) emits the fixed-width records, this
# native CPU stage finalizes them, and the independent Python implementation
# replays the retained export.  The current measured worker does not yet emit
# those records.
add_executable(sparkinterval-tg-platt-pt21-native-finalizer
  reference/tg_platt_pt21_native_finalizer.cpp
)
target_include_directories(
  sparkinterval-tg-platt-pt21-native-finalizer PRIVATE gpu/include
)
target_compile_options(
  sparkinterval-tg-platt-pt21-native-finalizer PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
)

# Qualification-only accelerator for the two scalar Python packet scans in
# the PT21 native-record adapter.  GMP is necessary for the complete accepted
# binary64 language (subnormal denominators reach 2^1074); the reference
# Python Fraction path remains the default when these optional libraries are
# unavailable.
find_library(SPARKINTERVAL_PT21_FASTPATH_GMPXX_LIBRARY NAMES gmpxx)
find_library(SPARKINTERVAL_PT21_FASTPATH_GMP_LIBRARY NAMES gmp)
if(SPARKINTERVAL_PT21_FASTPATH_GMPXX_LIBRARY
   AND SPARKINTERVAL_PT21_FASTPATH_GMP_LIBRARY)
  add_executable(sparkinterval-tg-platt-pt21-native-scan-fastpath
    reference/tg_platt_pt21_packet_scan_fastpath.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-pt21-native-scan-fastpath PRIVATE gpu/include
  )
  target_link_libraries(
    sparkinterval-tg-platt-pt21-native-scan-fastpath PRIVATE
    "${SPARKINTERVAL_PT21_FASTPATH_GMPXX_LIBRARY}"
    "${SPARKINTERVAL_PT21_FASTPATH_GMP_LIBRARY}"
  )
  target_compile_options(
    sparkinterval-tg-platt-pt21-native-scan-fastpath PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-ffp-contract=off;-Wall;-Wextra;-Wpedantic;-Werror>
  )

  # Explicitly selected native streaming checker for the canonical v2 block
  # artifact.  It recomputes the whole exact-rational document the Python
  # reference finalizer produces and must stay byte-identical to it; the
  # Python builder remains the independent implementation and the default.
  add_executable(sparkinterval-tg-platt-pt21-native-artifact-builder
    reference/tg_platt_pt21_native_artifact_builder.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-pt21-native-artifact-builder PRIVATE gpu/include
  )
  target_link_libraries(
    sparkinterval-tg-platt-pt21-native-artifact-builder PRIVATE
    "${SPARKINTERVAL_PT21_FASTPATH_GMPXX_LIBRARY}"
    "${SPARKINTERVAL_PT21_FASTPATH_GMP_LIBRARY}"
  )
  target_compile_options(
    sparkinterval-tg-platt-pt21-native-artifact-builder PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-ffp-contract=off;-Wall;-Wextra;-Wpedantic;-Werror>
  )
endif()

if(SPARKINTERVAL_BUILD_TG_CDEM)
  find_package(Threads REQUIRED)
  add_executable(sparkinterval-tg-cdem-abel
    reference/tg_cdem_abel.cpp
  )
  target_include_directories(sparkinterval-tg-cdem-abel PRIVATE gpu/include)
  target_link_libraries(sparkinterval-tg-cdem-abel PRIVATE OpenMP::OpenMP_CXX)
  target_compile_options(sparkinterval-tg-cdem-abel PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )
  add_executable(sparkinterval-tg-cdem-abel-chunk-replay
    reference/tg_cdem_abel_chunk_replay.cpp
  )
  target_compile_options(sparkinterval-tg-cdem-abel-chunk-replay PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O2;-Wall;-Wextra;-Werror>
  )
  add_executable(sparkinterval-tg-cdem-abel-measured-workload
    reference/tg_cdem_abel_measured_workload.cpp
  )
  target_include_directories(
    sparkinterval-tg-cdem-abel-measured-workload PRIVATE gpu/include
  )
  target_link_libraries(
    sparkinterval-tg-cdem-abel-measured-workload PRIVATE Threads::Threads
  )
  target_compile_options(sparkinterval-tg-cdem-abel-measured-workload PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )
  add_executable(sparkinterval-tg-cdem-abel-artifact-terminal
    reference/tg_cdem_abel_artifact_terminal.cpp
  )
  target_include_directories(
    sparkinterval-tg-cdem-abel-artifact-terminal PRIVATE gpu/include
  )
  target_link_libraries(
    sparkinterval-tg-cdem-abel-artifact-terminal PRIVATE Threads::Threads
  )
  target_compile_options(
    sparkinterval-tg-cdem-abel-artifact-terminal PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )
endif()

if(SPARKINTERVAL_BUILD_TG_PROP1224)
  add_executable(sparkinterval-tg-prop1224-factor-shard
    reference/tg_prop1224_factor_shard.cpp
  )
  target_include_directories(sparkinterval-tg-prop1224-factor-shard PRIVATE
    gpu/include
  )
  target_compile_options(sparkinterval-tg-prop1224-factor-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-Wall;-Wextra;-Werror>
  )
endif()

if(SPARKINTERVAL_BUILD_TG_PROP1224_MPFR)
  find_path(SPARKINTERVAL_MPFR_INCLUDE_DIR mpfr.h REQUIRED)
  find_library(SPARKINTERVAL_MPFR_LIBRARY NAMES mpfr REQUIRED)
  find_library(SPARKINTERVAL_GMPXX_LIBRARY NAMES gmpxx REQUIRED)
  find_library(SPARKINTERVAL_GMP_LIBRARY NAMES gmp REQUIRED)
  add_executable(sparkinterval-tg-prop1224-mpfr-shard
    reference/tg_prop1224_mpfr_shard.cpp
  )
  target_include_directories(sparkinterval-tg-prop1224-mpfr-shard PRIVATE
    gpu/include
    ${SPARKINTERVAL_MPFR_INCLUDE_DIR}
  )
  target_link_libraries(sparkinterval-tg-prop1224-mpfr-shard PRIVATE
    ${SPARKINTERVAL_MPFR_LIBRARY}
    ${SPARKINTERVAL_GMPXX_LIBRARY}
    ${SPARKINTERVAL_GMP_LIBRARY}
  )
  target_compile_options(sparkinterval-tg-prop1224-mpfr-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-Wall;-Wextra;-Werror>
  )
endif()

if(SPARKINTERVAL_BUILD_TG_GOLDBACH_LADDER)
  find_path(SPARKINTERVAL_GMP_INCLUDE_DIR gmp.h REQUIRED)
  find_library(SPARKINTERVAL_GMP_LIBRARY NAMES gmp REQUIRED)
  set(SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE
      "${CMAKE_CURRENT_SOURCE_DIR}/reference/tg_goldbach_ladder_native.cpp")
  file(SHA256 "${SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE}"
       SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256)
  add_executable(sparkinterval-tg-goldbach-ladder-native
    "${SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE}"
  )
  target_include_directories(sparkinterval-tg-goldbach-ladder-native PRIVATE
    "${SPARKINTERVAL_GMP_INCLUDE_DIR}"
  )
  target_compile_definitions(sparkinterval-tg-goldbach-ladder-native PRIVATE
    SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256="${SPARKINTERVAL_TG_GOLDBACH_NATIVE_SOURCE_SHA256}"
  )
  target_link_libraries(sparkinterval-tg-goldbach-ladder-native PRIVATE
    "${SPARKINTERVAL_GMP_LIBRARY}"
  )
  target_compile_options(sparkinterval-tg-goldbach-ladder-native PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-Wall;-Wextra;-Werror>
  )
endif()

if(SPARKINTERVAL_HURST_MERTENS_ROOT)
  add_executable(sparkinterval-tg-hurst-residual-shard
    reference/tg_hurst_residual_shard.cpp
    "${SPARKINTERVAL_HURST_MERTENS_ROOT}/sieve/SegmentedMobiusSieve.cpp"
  )
  target_include_directories(sparkinterval-tg-hurst-residual-shard PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    "${SPARKINTERVAL_HURST_MERTENS_ROOT}/sieve"
  )
  target_compile_definitions(sparkinterval-tg-hurst-residual-shard PRIVATE
    SPARKINTERVAL_HURST_UPSTREAM_COMMIT="fb47790c876c92690fce62990199ce961c5bdd72"
    USE_BUCKET_SIEVE=1
    SIEVE_NARROW_ENTRY=1
    SIEVE_SUB_BUCKETS=0
    $<$<STREQUAL:${CMAKE_SYSTEM_PROCESSOR},x86_64>:USE_DIVISION_FREE=1>
    $<$<NOT:$<STREQUAL:${CMAKE_SYSTEM_PROCESSOR},x86_64>>:USE_DIVISION_FREE=0>
  )
  target_link_libraries(sparkinterval-tg-hurst-residual-shard PRIVATE
    OpenMP::OpenMP_CXX
  )
  target_compile_options(sparkinterval-tg-hurst-residual-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-fno-strict-overflow;-Wall;-Wextra>
  )
endif()

if(SPARKINTERVAL_PSI_PRIMESIEVE_ROOT)
  # primesieve has a modern CMake build.  Its generic option names are fixed
  # only for this explicitly enabled source-scale adapter configuration.  A
  # block prevents those generic names from changing later project targets.
  block()
    set(BUILD_PRIMESIEVE OFF)
    set(BUILD_STATIC_LIBS ON)
    set(BUILD_SHARED_LIBS OFF)
    set(BUILD_DOC OFF)
    set(BUILD_MANPAGE OFF)
    set(BUILD_EXAMPLES OFF)
    set(BUILD_TESTS OFF)
    set(WITH_MULTIARCH ON)
    add_subdirectory(
      "${SPARKINTERVAL_PSI_PRIMESIEVE_ROOT}"
      "${CMAKE_CURRENT_BINARY_DIR}/psi-primesieve"
      EXCLUDE_FROM_ALL
    )
  endblock()

  # CRlibm's reviewed checkout predates an out-of-tree CMake build.  Build a
  # private copied source tree with its own Autotools recipe, leaving the
  # verified checkout pristine.  The upstream library remains LGPL-2.1+ and
  # is not copied into the SparkInterval source tree.
  include(ExternalProject)
  find_program(SPARKINTERVAL_GNU_MAKE NAMES make gmake REQUIRED)
  foreach(SPARKINTERVAL_AUTOTOOL IN ITEMS aclocal autoheader autoconf automake)
    find_program(
      SPARKINTERVAL_${SPARKINTERVAL_AUTOTOOL}_EXECUTABLE
      NAMES ${SPARKINTERVAL_AUTOTOOL}
      REQUIRED
    )
  endforeach()
  set(
    SPARKINTERVAL_PSI_CRLIBM_STAGE
    "${CMAKE_CURRENT_BINARY_DIR}/psi-crlibm/src/sparkinterval_psi_crlibm_external"
  )
  ExternalProject_Add(sparkinterval_psi_crlibm_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/psi-crlibm"
    SOURCE_DIR "${SPARKINTERVAL_PSI_CRLIBM_STAGE}"
    DOWNLOAD_COMMAND
      "${CMAKE_COMMAND}" -E copy_directory
      "${SPARKINTERVAL_PSI_CRLIBM_ROOT}"
      "${SPARKINTERVAL_PSI_CRLIBM_STAGE}"
    UPDATE_COMMAND ""
    PATCH_COMMAND ""
    CONFIGURE_COMMAND
      "${CMAKE_COMMAND}" -E env
      "CFLAGS=-O3 -fno-fast-math -fno-associative-math -ffp-contract=off -frounding-math -fexcess-precision=standard"
      "${CMAKE_COMMAND}" -E chdir "${SPARKINTERVAL_PSI_CRLIBM_STAGE}"
      "${SPARKINTERVAL_PSI_CRLIBM_STAGE}/prepare"
    BUILD_COMMAND
      "${SPARKINTERVAL_GNU_MAKE}" -C "${SPARKINTERVAL_PSI_CRLIBM_STAGE}"
    TEST_COMMAND
      "${SPARKINTERVAL_GNU_MAKE}" -C "${SPARKINTERVAL_PSI_CRLIBM_STAGE}"
      check
    INSTALL_COMMAND ""
    BUILD_BYPRODUCTS "${SPARKINTERVAL_PSI_CRLIBM_STAGE}/libcrlibm.a"
  )
  add_library(sparkinterval_psi_crlibm STATIC IMPORTED GLOBAL)
  set_target_properties(sparkinterval_psi_crlibm PROPERTIES
    IMPORTED_LOCATION "${SPARKINTERVAL_PSI_CRLIBM_STAGE}/libcrlibm.a"
  )
  add_dependencies(sparkinterval_psi_crlibm sparkinterval_psi_crlibm_external)

  add_executable(sparkinterval-tg-psi-residual-shard
    reference/tg_psi_residual_shard.cpp
  )
  target_include_directories(sparkinterval-tg-psi-residual-shard PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    "${SPARKINTERVAL_PSI_CRLIBM_ROOT}"
  )
  target_compile_definitions(sparkinterval-tg-psi-residual-shard PRIVATE
    SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT="4f85384851da23c36c01ec01ef85b5d9d246e556"
    SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT="eb3063791aa75bc9705b49283bf14250465220a7"
  )
  target_link_libraries(sparkinterval-tg-psi-residual-shard PRIVATE
    primesieve::primesieve
    sparkinterval_psi_crlibm
    m
  )
  target_compile_options(sparkinterval-tg-psi-residual-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-fno-fast-math;-fno-associative-math;-ffp-contract=off;-frounding-math;-Wall;-Wextra>
  )

  # A source-identical literal oracle keeps the old per-event integer-square-
  # root filter and runtime mode dispatch available for qualification.  It is
  # not the production worker.
  add_executable(sparkinterval-tg-psi-residual-shard-literal-reference
    reference/tg_psi_residual_shard.cpp
  )
  target_include_directories(
    sparkinterval-tg-psi-residual-shard-literal-reference PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    "${SPARKINTERVAL_PSI_CRLIBM_ROOT}"
  )
  target_compile_definitions(
    sparkinterval-tg-psi-residual-shard-literal-reference PRIVATE
    SPARKINTERVAL_PSI_LITERAL_REFERENCE=1
    SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT="4f85384851da23c36c01ec01ef85b5d9d246e556"
    SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT="eb3063791aa75bc9705b49283bf14250465220a7"
  )
  target_link_libraries(
    sparkinterval-tg-psi-residual-shard-literal-reference PRIVATE
    primesieve::primesieve
    sparkinterval_psi_crlibm
    m
  )
  target_compile_options(
    sparkinterval-tg-psi-residual-shard-literal-reference PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-fno-fast-math;-fno-associative-math;-ffp-contract=off;-frounding-math;-Wall;-Wextra>
  )

  add_executable(sparkinterval-tg-psi-affine-guard-shard
    reference/tg_psi_affine_guard_shard.cpp
  )
  target_include_directories(sparkinterval-tg-psi-affine-guard-shard PRIVATE
    gpu/include
    ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
    "${SPARKINTERVAL_PSI_CRLIBM_ROOT}"
  )
  target_compile_definitions(sparkinterval-tg-psi-affine-guard-shard PRIVATE
    SPARKINTERVAL_PRIMESIEVE_UPSTREAM_COMMIT="4f85384851da23c36c01ec01ef85b5d9d246e556"
    SPARKINTERVAL_CRLIBM_UPSTREAM_COMMIT="eb3063791aa75bc9705b49283bf14250465220a7"
  )
  target_link_libraries(sparkinterval-tg-psi-affine-guard-shard PRIVATE
    primesieve::primesieve
    sparkinterval_psi_crlibm
    m
  )
  target_compile_options(sparkinterval-tg-psi-affine-guard-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-march=native;-mtune=native;-fno-fast-math;-fno-associative-math;-ffp-contract=off;-frounding-math;-Wall;-Wextra>
  )
endif()

if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  find_path(
    SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR
    flint/acb_dirichlet.h
    PATHS "${SPARKINTERVAL_FLINT_PLATT_PREFIX}/include"
    NO_DEFAULT_PATH
    REQUIRED
  )
  find_library(
    SPARKINTERVAL_FLINT_PLATT_LIBRARY
    NAMES flint
    PATHS "${SPARKINTERVAL_FLINT_PLATT_PREFIX}/lib"
    NO_DEFAULT_PATH
    REQUIRED
  )
  find_library(SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY NAMES gmp REQUIRED)
  add_executable(sparkinterval-tg-platt-zeta-shard
    reference/tg_platt_zeta_shard.cpp
  )
  target_include_directories(sparkinterval-tg-platt-zeta-shard PRIVATE
    gpu/include
    "${SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR}"
  )
  target_compile_definitions(sparkinterval-tg-platt-zeta-shard PRIVATE
    SPARKINTERVAL_FLINT_PLATT_COMMIT="8d5454b96761fafe4d5a9da76a369a602f500f49"
  )
  target_link_libraries(sparkinterval-tg-platt-zeta-shard PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_LIBRARY}"
    "${SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY}"
    m
  )
  target_compile_options(sparkinterval-tg-platt-zeta-shard PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )

  add_executable(sparkinterval-tg-platt-gamma-taylor
    reference/tg_platt_gamma_taylor.cpp
  )
  target_include_directories(sparkinterval-tg-platt-gamma-taylor PRIVATE
    gpu/include
    "${SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR}"
  )
  target_compile_definitions(sparkinterval-tg-platt-gamma-taylor PRIVATE
    SPARKINTERVAL_FLINT_PLATT_COMMIT="8d5454b96761fafe4d5a9da76a369a602f500f49"
  )
  target_link_libraries(sparkinterval-tg-platt-gamma-taylor PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_LIBRARY}"
    "${SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY}"
    m
  )
  target_compile_options(sparkinterval-tg-platt-gamma-taylor PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )

  add_executable(sparkinterval-tg-platt-gamma-taylor-v2
    reference/tg_platt_gamma_taylor_stream_v2.cpp
  )
  target_include_directories(sparkinterval-tg-platt-gamma-taylor-v2 PRIVATE
    gpu/include
    "${SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR}"
  )
  target_compile_definitions(sparkinterval-tg-platt-gamma-taylor-v2 PRIVATE
    SPARKINTERVAL_FLINT_PLATT_COMMIT="8d5454b96761fafe4d5a9da76a369a602f500f49"
  )
  target_link_libraries(sparkinterval-tg-platt-gamma-taylor-v2 PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_LIBRARY}"
    "${SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY}"
    m
  )
  target_compile_options(sparkinterval-tg-platt-gamma-taylor-v2 PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
  )

  # Bounded CPU/FLINT fallback for the adaptive stationary-point cases
  # emitted by the PT21 three-stream scanner.  This target checks only the
  # finite interpolation/replay boundary; it does not assert the missing
  # Hardy-Z or analytic Turing realizations.
  add_library(sparkinterval-tg-platt-stationary-resolver-core STATIC
    reference/tg_platt_stationary_resolver.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-stationary-resolver-core PUBLIC
    gpu/include
    PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR}"
  )
  target_link_libraries(
    sparkinterval-tg-platt-stationary-resolver-core PUBLIC
    "${SPARKINTERVAL_FLINT_PLATT_LIBRARY}"
    "${SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY}"
    m
  )
  target_compile_options(
    sparkinterval-tg-platt-stationary-resolver-core PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
  )

  add_executable(sparkinterval-tg-platt-stationary-resolver
    reference/tg_platt_stationary_resolver_benchmark.cpp
  )
  target_link_libraries(
    sparkinterval-tg-platt-stationary-resolver PRIVATE
    sparkinterval-tg-platt-stationary-resolver-core
  )
  target_compile_options(
    sparkinterval-tg-platt-stationary-resolver PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
  )

  if(TARGET sparkinterval-tg-platt-event-scan)
    add_library(sparkinterval-tg-platt-stationary-junction STATIC
      reference/tg_platt_stationary_junction.cpp
    )
    target_include_directories(
      sparkinterval-tg-platt-stationary-junction PUBLIC gpu/include
    )
    target_link_libraries(
      sparkinterval-tg-platt-stationary-junction PUBLIC
      sparkinterval-tg-platt-event-scan
      sparkinterval-tg-platt-stationary-resolver-core
    )
    target_compile_features(
      sparkinterval-tg-platt-stationary-junction PUBLIC cxx_std_20
    )
    target_compile_options(
      sparkinterval-tg-platt-stationary-junction PRIVATE
      $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
    )

    add_executable(sparkinterval-tg-platt-stationary-junction-benchmark
      reference/tg_platt_stationary_junction_benchmark.cu
    )
    target_include_directories(
      sparkinterval-tg-platt-stationary-junction-benchmark PRIVATE gpu/include
    )
    set_target_properties(
      sparkinterval-tg-platt-stationary-junction-benchmark PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
      CUDA_RESOLVE_DEVICE_SYMBOLS ON
      LINKER_LANGUAGE CUDA
    )
    target_compile_options(
      sparkinterval-tg-platt-stationary-junction-benchmark PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    target_link_libraries(
      sparkinterval-tg-platt-stationary-junction-benchmark PRIVATE
      sparkinterval-tg-platt-stationary-junction
      sparkinterval-tg-platt-event-scan
    )

    # Qualification-only fusion of the V2 source worker with the finite
    # stationary junction.  The normal V2 target above is intentionally
    # unchanged; this distinct identity emits only PT21IQH1/PT21IQF1/PT21IQT1
    # nonterminal evidence and keeps every analytic/source claim false.
    add_executable(
      sparkinterval-tg-platt-inline-stationary-qualification
      gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu
      gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
    )
    target_include_directories(
      sparkinterval-tg-platt-inline-stationary-qualification
      PRIVATE gpu/include
    )
    set_target_properties(
      sparkinterval-tg-platt-inline-stationary-qualification PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
    )
    target_compile_definitions(
      sparkinterval-tg-platt-inline-stationary-qualification PRIVATE
      SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
      SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION=1
    )
    target_compile_options(
      sparkinterval-tg-platt-inline-stationary-qualification PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    target_link_libraries(
      sparkinterval-tg-platt-inline-stationary-qualification PRIVATE
      sparkinterval-tg-platt-dd-accumulator
      sparkinterval-tg-platt-dd-transform
      sparkinterval-tg-platt-event-scan
      sparkinterval-tg-platt-stationary-junction
      Threads::Threads
    )

    add_executable(sparkinterval-tg-platt-inline-stationary-kat
      reference/tg_platt_inline_stationary_kat.cu
    )
    target_include_directories(
      sparkinterval-tg-platt-inline-stationary-kat PRIVATE gpu/include
    )
    set_target_properties(
      sparkinterval-tg-platt-inline-stationary-kat PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_SEPARABLE_COMPILATION ON
      CUDA_RESOLVE_DEVICE_SYMBOLS ON
      LINKER_LANGUAGE CUDA
    )
    target_compile_options(
      sparkinterval-tg-platt-inline-stationary-kat PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    target_link_libraries(
      sparkinterval-tg-platt-inline-stationary-kat PRIVATE
      sparkinterval-tg-platt-stationary-junction
      sparkinterval-tg-platt-event-scan
    )
  endif()

  if(TARGET sparkinterval-h100-tg-platt-event-scan)
      add_library(
        sparkinterval-h100-tg-platt-stationary-junction STATIC
        reference/tg_platt_stationary_junction.cpp
      )
      target_include_directories(
        sparkinterval-h100-tg-platt-stationary-junction PUBLIC gpu/include
      )
      target_link_libraries(
        sparkinterval-h100-tg-platt-stationary-junction PUBLIC
        sparkinterval-h100-tg-platt-event-scan
        sparkinterval-tg-platt-stationary-resolver-core
      )
      target_compile_features(
        sparkinterval-h100-tg-platt-stationary-junction PUBLIC cxx_std_20
      )
      target_compile_options(
        sparkinterval-h100-tg-platt-stationary-junction PRIVATE
        $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
      )

      add_executable(
        sparkinterval-h100-tg-platt-inline-stationary-qualification
        gpu/platform/h100/h100_tg_platt_fused_source_worker_v2.cu
        gpu/platform/h100/tg_platt_gamma_dd_gpu.cu
      )
      sparkinterval_configure_h100_kernel(
        sparkinterval-h100-tg-platt-inline-stationary-qualification
      )
      set_target_properties(
        sparkinterval-h100-tg-platt-inline-stationary-qualification PROPERTIES
        CUDA_STANDARD 20
        CUDA_STANDARD_REQUIRED ON
      )
      target_compile_definitions(
        sparkinterval-h100-tg-platt-inline-stationary-qualification PRIVATE
        SPARKINTERVAL_CMAKE_BUILD_CONFIG="$<CONFIG>"
        SPARKINTERVAL_REQUIRE_H100_SM90=1
        SPARKINTERVAL_PT21_INLINE_STATIONARY_QUALIFICATION=1
      )
      target_link_libraries(
        sparkinterval-h100-tg-platt-inline-stationary-qualification PRIVATE
        sparkinterval-h100-tg-platt-dd-accumulator
        sparkinterval-h100-tg-platt-dd-transform
        sparkinterval-h100-tg-platt-event-scan
        sparkinterval-h100-tg-platt-stationary-junction
        Threads::Threads
      )
  endif()

  # Source-shaped one-sided Turing arithmetic inputs for each PT21 block.
  # This target emits only rigorous Arb enclosures for the elementary and
  # log-Gamma terms; the analytic Turing realization remains a separate
  # theorem/receipt boundary.
  add_executable(sparkinterval-tg-platt-pt21-turing-inputs
    reference/tg_platt_pt21_turing_inputs.cpp
  )
  target_include_directories(
    sparkinterval-tg-platt-pt21-turing-inputs PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_INCLUDE_DIR}"
  )
  target_link_libraries(
    sparkinterval-tg-platt-pt21-turing-inputs PRIVATE
    "${SPARKINTERVAL_FLINT_PLATT_LIBRARY}"
    "${SPARKINTERVAL_FLINT_PLATT_GMP_LIBRARY}"
    m
  )
  target_compile_options(
    sparkinterval-tg-platt-pt21-turing-inputs PRIVATE
    $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
  )
endif()
target_include_directories(sparkinterval-tg-workload-benchmark PRIVATE gpu/include)
target_link_libraries(sparkinterval-tg-workload-benchmark PRIVATE
  sparkinterval_tg_workload_benchmark_kernel
  CUDA::cudart
)

add_library(sparkinterval_tg_r2star_factor_support_kernel STATIC
  gpu/src/tg_r2star_factor_support_kernel.cu
)
target_include_directories(
  sparkinterval_tg_r2star_factor_support_kernel PUBLIC gpu/include
)
set_target_properties(sparkinterval_tg_r2star_factor_support_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_tg_r2star_factor_support_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-tg-r2star-factor-support
  gpu/src/tg_r2star_factor_support_runner.cpp
)
target_include_directories(sparkinterval-tg-r2star-factor-support PRIVATE
  gpu/include
)
target_link_libraries(sparkinterval-tg-r2star-factor-support PRIVATE
  sparkinterval_tg_r2star_factor_support_kernel
  CUDA::cudart
)
target_compile_options(sparkinterval-tg-r2star-factor-support PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
)

add_library(sparkinterval_tg_r2star_chunk_kernel STATIC
  gpu/src/tg_r2star_chunk_kernel.cu
)
target_include_directories(sparkinterval_tg_r2star_chunk_kernel PUBLIC
  gpu/include
)
set_target_properties(sparkinterval_tg_r2star_chunk_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_tg_r2star_chunk_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-tg-r2star-chunk
  gpu/src/tg_r2star_chunk_runner.cpp
)
target_include_directories(sparkinterval-tg-r2star-chunk PRIVATE
  gpu/include
  ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
)
target_link_libraries(sparkinterval-tg-r2star-chunk PRIVATE
  sparkinterval_tg_r2star_factor_support_kernel
  sparkinterval_tg_r2star_chunk_kernel
  CUDA::cudart
)
target_compile_options(sparkinterval-tg-r2star-chunk PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
)

add_executable(sparkinterval-tg-r2star-arithmetic-replay
  reference/tg_r2star_arithmetic_replay.cpp
)
target_include_directories(
  sparkinterval-tg-r2star-arithmetic-replay PRIVATE
  gpu/include
  ${SPARKINTERVAL_BOOST_INCLUDE_DIR}
)
target_link_libraries(
  sparkinterval-tg-r2star-arithmetic-replay PRIVATE Threads::Threads
)
target_compile_options(
  sparkinterval-tg-r2star-arithmetic-replay PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
)

add_executable(sparkinterval-tg-r2star-replay-segment-partition-known-answers
  tests/tg_r2star_replay_segment_partition_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-r2star-replay-segment-partition-known-answers PRIVATE
  gpu/include
)
target_compile_options(
  sparkinterval-tg-r2star-replay-segment-partition-known-answers PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic;-Werror>
)

add_executable(sparkinterval-tg-r2star-transition-known-answers
  tests/tg_r2star_transition_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-r2star-transition-known-answers PRIVATE gpu/include
)
target_link_libraries(sparkinterval-tg-r2star-transition-known-answers PRIVATE
  sparkinterval_tg_r2star_chunk_kernel
  CUDA::cudart
)
target_compile_options(
  sparkinterval-tg-r2star-transition-known-answers PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror>
)

add_library(sparkinterval_tg_mobius_segment_kernel STATIC
  gpu/src/tg_mobius_segment_kernel.cu
)
target_compile_definitions(
  sparkinterval_tg_mobius_segment_kernel
  PUBLIC
    SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD=${SPARKINTERVAL_TG_MOBIUS_AFFINE_ROWS_PER_THREAD}
)
target_include_directories(
  sparkinterval_tg_mobius_segment_kernel PUBLIC gpu/include
)
set_target_properties(sparkinterval_tg_mobius_segment_kernel PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON
)
target_compile_options(sparkinterval_tg_mobius_segment_kernel PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
)

add_executable(sparkinterval-tg-mobius-segment
  gpu/src/tg_mobius_segment_runner.cpp
)
target_include_directories(sparkinterval-tg-mobius-segment PRIVATE gpu/include)
target_link_libraries(sparkinterval-tg-mobius-segment PRIVATE
  sparkinterval_tg_mobius_segment_kernel
  CUDA::cudart
)
target_compile_options(sparkinterval-tg-mobius-segment PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-mobius-persistent
  gpu/src/tg_mobius_persistent_runner.cpp
)
target_include_directories(
  sparkinterval-tg-mobius-persistent PRIVATE gpu/include
)
target_link_libraries(sparkinterval-tg-mobius-persistent PRIVATE
  sparkinterval_tg_mobius_segment_kernel
  CUDA::cudart
)
target_compile_options(sparkinterval-tg-mobius-persistent PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-mobius-affine-candidate-order-known-answers
  tests/tg_mobius_affine_candidate_order_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-mobius-affine-candidate-order-known-answers
  PRIVATE gpu/include
)
target_link_libraries(
  sparkinterval-tg-mobius-affine-candidate-order-known-answers
  PRIVATE CUDA::cudart
)
target_compile_options(
  sparkinterval-tg-mobius-affine-candidate-order-known-answers PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-mobius-fused-support-known-answers
  tests/tg_mobius_fused_support_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-mobius-fused-support-known-answers PRIVATE gpu/include
)
target_link_libraries(
  sparkinterval-tg-mobius-fused-support-known-answers PRIVATE
  sparkinterval_tg_mobius_segment_kernel
  CUDA::cudart
)
target_compile_options(
  sparkinterval-tg-mobius-fused-support-known-answers PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-mobius-residue23571113-known-answers
  tests/tg_mobius_residue23571113_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-mobius-residue23571113-known-answers PRIVATE gpu/include
)
target_link_libraries(
  sparkinterval-tg-mobius-residue23571113-known-answers PRIVATE
  sparkinterval_tg_mobius_segment_kernel
  CUDA::cudart
)
target_compile_options(
  sparkinterval-tg-mobius-residue23571113-known-answers PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-mobius-affine-scan-known-answers
  tests/tg_mobius_affine_scan_known_answers.cu
)
target_include_directories(
  sparkinterval-tg-mobius-affine-scan-known-answers PRIVATE gpu/include
)
target_link_libraries(
  sparkinterval-tg-mobius-affine-scan-known-answers PRIVATE
  sparkinterval_tg_mobius_segment_kernel
  CUDA::cudart
)
set_target_properties(
  sparkinterval-tg-mobius-affine-scan-known-answers PROPERTIES
  CUDA_STANDARD 17
  CUDA_STANDARD_REQUIRED ON
)

add_executable(sparkinterval-generated-driver-report-test
  tests/generated_driver_report_test.cpp
)
target_include_directories(sparkinterval-generated-driver-report-test PRIVATE
  gpu/src
)

add_executable(sparkinterval-sha256-test
  tests/sha256_test.cpp
)
target_include_directories(sparkinterval-sha256-test PRIVATE gpu/include)

add_executable(sparkinterval-tg-dirichlet-formulaic-qmajor-test
  tests/tg_dirichlet_formulaic_qmajor_known_answers.cpp
)
target_include_directories(
  sparkinterval-tg-dirichlet-formulaic-qmajor-test PRIVATE gpu/include
)
target_compile_features(
  sparkinterval-tg-dirichlet-formulaic-qmajor-test PRIVATE cxx_std_20
)
target_compile_options(
  sparkinterval-tg-dirichlet-formulaic-qmajor-test PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-tg-dirichlet-formulaic-qmajor-benchmark
  gpu/src/tg_dirichlet_formulaic_qmajor_benchmark.cpp
)
target_include_directories(
  sparkinterval-tg-dirichlet-formulaic-qmajor-benchmark PRIVATE gpu/include
)
target_compile_features(
  sparkinterval-tg-dirichlet-formulaic-qmajor-benchmark PRIVATE cxx_std_20
)
target_compile_options(
  sparkinterval-tg-dirichlet-formulaic-qmajor-benchmark PRIVATE
  $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang>:-O3;-Wall;-Wextra;-Werror>
)

add_executable(sparkinterval-measured-worker-scope-test
  tests/measured_worker_scope_known_answers.cpp
)
target_include_directories(
  sparkinterval-measured-worker-scope-test PRIVATE gpu/include
)

enable_testing()
add_test(
  NAME tg_dirichlet_chirp_recurrence_known_answers
  COMMAND $<TARGET_FILE:sparkinterval-tg-dirichlet-chirp-recurrence-benchmark>
          400000 4096 512 257 256
)
set_tests_properties(
  tg_dirichlet_chirp_recurrence_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;bluestein;chirp;mpfr;known-answer"
)
add_test(
  NAME tg_platt_pt21_native_finalizer_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_PLATT_PT21_NATIVE_FINALIZER=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-finalizer>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_platt_pt21_native_finalizer
)
set_tests_properties(
  tg_platt_pt21_native_finalizer_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;platt;pt21;native-finalizer;retained-replay;known-answer"
)
add_test(
  NAME tg_platt_pt21_native_record_adapter_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_PLATT_PT21_NATIVE_FINALIZER=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-finalizer>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_platt_pt21_native_record_adapter
)
set_tests_properties(
  tg_platt_pt21_native_record_adapter_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;platt;pt21;native-record-adapter;tamper;known-answer"
)
if(TARGET sparkinterval-tg-platt-pt21-native-scan-fastpath)
  add_test(
    NAME tg_platt_pt21_native_scan_fastpath_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            PYTHONPATH=${CMAKE_SOURCE_DIR}
            TG_PLATT_PT21_NATIVE_SCAN_FASTPATH=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-scan-fastpath>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_pt21_native_scan_fastpath
  )
  set_tests_properties(
    tg_platt_pt21_native_scan_fastpath_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;pt21;qualification-only;native-scan;gmp;tamper;known-answer"
  )
endif()
if(TARGET sparkinterval-tg-platt-pt21-native-artifact-builder)
  add_test(
    NAME tg_platt_pt21_native_artifact_builder_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            PYTHONPATH=${CMAKE_SOURCE_DIR}
            TG_PLATT_PT21_NATIVE_ARTIFACT_BUILDER=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-artifact-builder>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_pt21_native_artifact_builder
  )
  set_tests_properties(
    tg_platt_pt21_native_artifact_builder_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;pt21;qualification-only;native-artifact;gmp;byte-identity;known-answer"
  )
endif()
if(SPARKINTERVAL_BUILD_H100_NATIVE)
  add_test(
    NAME h100_native_cli_offline
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/test_h100_native_cli.py
            --probe $<TARGET_FILE:sparkinterval-h100-probe-runner>
            --primitive $<TARGET_FILE:sparkinterval-h100-interval-batch>
            --expression $<TARGET_FILE:sparkinterval-h100-expression-batch>
            --grh-lambda $<TARGET_FILE:sparkinterval-h100-grh-lambda>
            --factor-support
            $<TARGET_FILE:sparkinterval-h100-tg-r2star-factor-support>
            --r2star-chunk
            $<TARGET_FILE:sparkinterval-h100-tg-r2star-chunk>
            --mobius-segment
            $<TARGET_FILE:sparkinterval-h100-tg-mobius-segment>
            --mobius-persistent
            $<TARGET_FILE:sparkinterval-h100-tg-mobius-persistent>
            --probe-cubin ${SPARKINTERVAL_H100_PROBE_CUBIN}
            --cuobjdump ${SPARKINTERVAL_CUOBJDUMP}
  )
  set_tests_properties(h100_native_cli_offline PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
  add_test(
    NAME h100_runtime_policy_known_answers
    COMMAND sparkinterval-h100-runtime-policy-known-answers
  )
endif()
add_test(
  NAME generated_driver_report_json
  COMMAND sparkinterval-generated-driver-report-test
)
add_test(
  NAME generated_driver_host_validation
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/test_generated_driver_host.py
          --report-fixture
          $<TARGET_FILE:sparkinterval-generated-driver-report-test>
          --driver $<TARGET_FILE:sparkinterval-generated-driver>
)
add_test(NAME sha256_known_answers COMMAND sparkinterval-sha256-test)
add_test(
  NAME tg_dirichlet_formulaic_qmajor_known_answers
  COMMAND sparkinterval-tg-dirichlet-formulaic-qmajor-test
)
add_test(
  NAME measured_worker_scope_known_answers
  COMMAND sparkinterval-measured-worker-scope-test
)
add_test(
  NAME tg_integer_work_item_microbenchmark_smoke
  COMMAND sparkinterval-tg-workload-benchmark --count 64 --repetitions 1
)
add_test(
  NAME tg_r2star_factor_support_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_r2star_cuda_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-r2star-factor-support>
)
set_tests_properties(tg_r2star_factor_support_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  SKIP_RETURN_CODE 77
)
add_test(
  NAME tg_r2star_cuda_chunk_python_contract
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_r2star_cuda_chunk_contract.py
          --runner $<TARGET_FILE:sparkinterval-tg-r2star-chunk>
)
set_tests_properties(tg_r2star_cuda_chunk_python_contract PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  SKIP_RETURN_CODE 77
)
add_test(
  NAME tg_r2star_cpu_full_row_arithmetic_replay
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_R2STAR_ARITHMETIC_REPLAYER=$<TARGET_FILE:sparkinterval-tg-r2star-arithmetic-replay>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_r2star_arithmetic_replay
          tests.test_tg_r2star_benchmark
)
set_tests_properties(
  tg_r2star_cpu_full_row_arithmetic_replay PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;r2star;cpu;independent;full-row;known-answer"
)
add_test(
  NAME tg_r2star_replay_segment_partition_known_answers
  COMMAND sparkinterval-tg-r2star-replay-segment-partition-known-answers
)
set_tests_properties(
  tg_r2star_replay_segment_partition_known_answers PROPERTIES
  LABELS "tg;r2star;cpu;segment;known-answer"
)
add_test(
  NAME tg_r2star_transition_known_answers
  COMMAND sparkinterval-tg-r2star-transition-known-answers
)
add_test(
  NAME tg_mobius_segment_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_mobius_cuda_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-mobius-segment>
)
set_tests_properties(tg_mobius_segment_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_mobius_affine_candidate_order_known_answers
  COMMAND sparkinterval-tg-mobius-affine-candidate-order-known-answers
)
add_test(
  NAME tg_mobius_fused_support_known_answers
  COMMAND sparkinterval-tg-mobius-fused-support-known-answers
)
add_test(
  NAME tg_mobius_residue23571113_known_answers
  COMMAND sparkinterval-tg-mobius-residue23571113-known-answers
)
add_test(
  NAME tg_mobius_p13_seed_qualification_source_tests
  COMMAND ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_mobius_p13_seed_qualification
)
add_test(
  NAME tg_mobius_affine_scan_known_answers
  COMMAND sparkinterval-tg-mobius-affine-scan-known-answers
)
add_test(
  NAME tg_mobius_persistent_known_answers
  COMMAND
    ${Python3_EXECUTABLE}
    ${CMAKE_SOURCE_DIR}/tests/tg_mobius_persistent_known_answers.py
    --one-shot $<TARGET_FILE:sparkinterval-tg-mobius-segment>
    --persistent $<TARGET_FILE:sparkinterval-tg-mobius-persistent>
)
set_tests_properties(
  tg_mobius_persistent_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
set_tests_properties(
  tg_mobius_affine_candidate_order_known_answers
  tg_mobius_fused_support_known_answers
  tg_mobius_residue23571113_known_answers
  tg_mobius_p13_seed_qualification_source_tests
  tg_mobius_affine_scan_known_answers
  tg_mobius_persistent_known_answers
  PROPERTIES LABELS "tg;mobius;cuda;known-answer"
)
add_test(
  NAME tg_dirichlet_lattice_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_lattice_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-lattice>
          --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-lattice-exact>
)
set_tests_properties(tg_dirichlet_lattice_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_fused_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_fused_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-fused>
          --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-fused-exact>
)
set_tests_properties(tg_dirichlet_fused_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_allchars_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
          --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
)
set_tests_properties(tg_dirichlet_allchars_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
if(SPARKINTERVAL_ENABLE_SLOW_QUALIFICATION_TESTS)
  add_test(
    NAME tg_dirichlet_allchars_max_order_impulse_qualification
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_impulse_qualification.py
      --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
      --device 0
      --maximum-seconds 300
  )
  set_tests_properties(
    tg_dirichlet_allchars_max_order_impulse_qualification PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 330
    LABELS "tg;dirichlet;bluestein;cuda;maximum-order;qualification;slow"
  )
  add_test(
    NAME tg_dirichlet_allchars_max_order_delta_one_qualification
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_allchars_max_order_delta_one_qualification.py
      --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
      --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
      --device 0
      --maximum-seconds 300
      --checker-timeout 120
  )
  set_tests_properties(
    tg_dirichlet_allchars_max_order_delta_one_qualification PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 480
    LABELS "tg;dirichlet;bluestein;cuda;maximum-order;delta-one;mpfr;qualification;slow"
  )
  add_test(
    NAME tg_dirichlet_fft_root_recurrence_qualification
    COMMAND
      ${Python3_EXECUTABLE}
      ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_fft_root_recurrence_qualification.py
      --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
      --checker $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
      --command-timeout 120
  )
  set_tests_properties(
    tg_dirichlet_fft_root_recurrence_qualification PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 600
    LABELS "tg;dirichlet;fft;roots;mpfr;qualification;slow"
  )
endif()
add_test(
  NAME tg_dirichlet_resident_handoff_known_answers
  COMMAND
    ${Python3_EXECUTABLE}
    ${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_TOOL}
    run
    --directory
    ${SPARKINTERVAL_TG_DIRICHLET_RESIDENT_HANDOFF_FIXTURE_DIR}/ctest
    --runner
    $<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
    --device 0
)
set_tests_properties(
  tg_dirichlet_resident_handoff_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_residue_composition_mpfr_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_residue_composition_mpfr_kat.py
          --checker
          $<TARGET_FILE:sparkinterval-tg-dirichlet-residue-composition-mpfr>
)
set_tests_properties(
  tg_dirichlet_residue_composition_mpfr_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_largeq_batch_known_answers
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tests/tg_dirichlet_largeq_batch_known_answers.py
          --runner $<TARGET_FILE:sparkinterval-tg-dirichlet-largeq-batch>
          --lattice-checker
          $<TARGET_FILE:sparkinterval-tg-dirichlet-lattice-exact>
          --composition-checker
          $<TARGET_FILE:sparkinterval-tg-dirichlet-residue-composition-mpfr>
)
set_tests_properties(tg_dirichlet_largeq_batch_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_tmajor_row_resident_seeded_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_DIRICHLET_TMAJOR_SEEDED_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-largeq-seeded>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_tmajor_cuda_block
)
set_tests_properties(
  tg_dirichlet_tmajor_row_resident_seeded_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;largeq;tmajor;cuda;known-answer"
)
add_test(
  NAME tg_dirichlet_formulaic_qmajor_service_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_DIRICHLET_TMAJOR_SEEDED_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-largeq-seeded>
          TG_DIRICHLET_ALLCHARS_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-allchars>
          TG_DIRICHLET_ALLCHARS_MPFR_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-allchars-mpfr>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_formulaic_qmajor_service
)
set_tests_properties(
  tg_dirichlet_formulaic_qmajor_service_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;largeq;formulaic;qmajor;cuda;known-answer;attack"
)
add_test(
  NAME tg_dirichlet_resident_qmajor_phase_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_DIRICHLET_TMAJOR_SEEDED_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-largeq-seeded>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_resident_qmajor_phase
)
set_tests_properties(
  tg_dirichlet_resident_qmajor_phase_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;largeq;resident;qmajor;cuda;known-answer;attack"
)
add_test(
  NAME tg_dirichlet_resident_qmajor_stream_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_DIRICHLET_RESIDENT_STREAM_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-resident-qmajor-stream>
          TG_DIRICHLET_TMAJOR_SEEDED_BINARY=$<TARGET_FILE:sparkinterval-tg-dirichlet-largeq-seeded>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_resident_qmajor_stream
          tests.test_tg_dirichlet_cache_resident_feed
)
set_tests_properties(
  tg_dirichlet_resident_qmajor_stream_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;largeq;resident;qmajor;stream;cuda;known-answer;attack"
)
add_test(
  NAME tg_dirichlet_booker_smallq_certified_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          TG_SMALLQ_CERTIFIED_RUNNER=$<TARGET_FILE:sparkinterval-tg-dirichlet-booker-smallq-certified>
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_booker_smallq_certified
          tests.test_tg_dirichlet_booker_smallq_factored
          tests.test_tg_dirichlet_booker_smallq_packed_stream_v1
)
set_tests_properties(
  tg_dirichlet_booker_smallq_certified_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
add_test(
  NAME tg_dirichlet_strict_sign_pack_device_known_answers
  COMMAND sparkinterval-tg-dirichlet-strict-sign-pack-kat
)
set_tests_properties(
  tg_dirichlet_strict_sign_pack_device_known_answers PROPERTIES
  LABELS "tg;dirichlet;smallq;strict-sign;device;known-answer"
)
add_test(
  NAME tg_dirichlet_completed_sign_reducer_device_known_answers
  COMMAND sparkinterval-tg-dirichlet-completed-sign-reducer-kat
)
set_tests_properties(
  tg_dirichlet_completed_sign_reducer_device_known_answers PROPERTIES
  LABELS "tg;dirichlet;largeq;cuda;completed-l;compact-state;known-answer;attack"
)
add_test(
  NAME tg_dirichlet_resident_phase_accumulator_device_known_answers
  COMMAND sparkinterval-tg-dirichlet-resident-phase-accumulator-kat
)
set_tests_properties(
  tg_dirichlet_resident_phase_accumulator_device_known_answers PROPERTIES
  LABELS "tg;dirichlet;largeq;cuda;completed-l;cub;compact-state;known-answer;attack"
)
add_test(
  NAME tg_dirichlet_completed_sign_reducer_model_known_answers
  COMMAND ${CMAKE_COMMAND} -E env
          PYTHONPATH=${CMAKE_SOURCE_DIR}
          ${Python3_EXECUTABLE} -m unittest -v
          tests.test_tg_dirichlet_completed_sign_gpu_reducer
)
set_tests_properties(
  tg_dirichlet_completed_sign_reducer_model_known_answers PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  LABELS "tg;dirichlet;largeq;completed-l;memory-model;known-answer;attack"
)
if(SPARKINTERVAL_BUILD_TG_CDEM)
  add_test(
    NAME tg_cdem_abel_small_smoke
    COMMAND sparkinterval-tg-cdem-abel 10 40 7
  )
  add_test(
    NAME tg_cdem_abel_chunk_replay_known_answer
    COMMAND sparkinterval-tg-cdem-abel-chunk-replay 10 1 7 0
  )
  add_test(
    NAME tg_cdem_abel_measured_workload_rejects_unregistered_mode
    COMMAND sparkinterval-tg-cdem-abel-measured-workload --shell
  )
  set_tests_properties(
    tg_cdem_abel_measured_workload_rejects_unregistered_mode
    PROPERTIES WILL_FAIL TRUE
  )
  add_test(
    NAME tg_cdem_abel_artifact_terminal_rejects_unregistered_mode
    COMMAND sparkinterval-tg-cdem-abel-artifact-terminal --shell
  )
  set_tests_properties(
    tg_cdem_abel_artifact_terminal_rejects_unregistered_mode
    PROPERTIES WILL_FAIL TRUE
  )
endif()
if(SPARKINTERVAL_BUILD_TG_PROP1224)
  add_test(
    NAME tg_prop1224_factor_shard_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_prop1224_factor_shard_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-prop1224-factor-shard>
  )
  set_tests_properties(tg_prop1224_factor_shard_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_BUILD_TG_PROP1224_MPFR)
  add_test(
    NAME tg_prop1224_mpfr_shard_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_prop1224_mpfr_shard_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-prop1224-mpfr-shard>
  )
  set_tests_properties(tg_prop1224_mpfr_shard_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_BUILD_TG_GOLDBACH_LADDER)
  add_test(
    NAME tg_goldbach_ladder_native_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_goldbach_ladder_native_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-goldbach-ladder-native>
  )
  set_tests_properties(tg_goldbach_ladder_native_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_BUILD_TG_GOLDBACH_BUCKET_SIEVE)
  add_test(
    NAME tg_goldbach_bucket_sieve_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_goldbach_bucket_sieve_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-goldbach-bucket-sieve>
  )
  set_tests_properties(tg_goldbach_bucket_sieve_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_BUILD_TG_GOLDBACH_TILE_SIEVE)
  add_test(
    NAME tg_goldbach_tile_sieve_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_goldbach_tile_sieve_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-goldbach-tile-sieve>
  )
  set_tests_properties(tg_goldbach_tile_sieve_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_BUILD_TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION)
  add_test(
    NAME tg_goldbach_word_owner_wheel23_qualification_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_GOLDBACH_WORD_OWNER_WHEEL23_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-goldbach-word-owner-wheel23-qualification>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_goldbach_word_owner_wheel23_qualification
  )
  set_tests_properties(
    tg_goldbach_word_owner_wheel23_qualification_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    TIMEOUT 300
    LABELS "tg;goldbach;word-owner;wheel23;cuda;qualification;known-answer"
  )
endif()
if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE)
  add_test(
    NAME tg_platt_dd_accumulator_device_api_smoke
    COMMAND sparkinterval-tg-platt-dd-accumulator-api-smoke
  )
  set_tests_properties(
    tg_platt_dd_accumulator_device_api_smoke PROPERTIES
    LABELS "tg;platt;source;disk;cuda;device-api;slow"
  )
  add_test(
    NAME tg_platt_windowed_core_smoke
    COMMAND sparkinterval-tg-platt-windowed-core
            --terms=4096 --stages=4 --blocks=2 --repetitions=1
  )
  add_test(
    NAME tg_platt_windowed_fixed_phase_smoke
    COMMAND sparkinterval-tg-platt-windowed-core
            --terms=256 --stages=2 --blocks=260 --repetitions=1
            --reanchor-blocks=64 --source-geometry
  )
  add_test(
    NAME tg_platt_windowed_gamma_synthesis_smoke
    COMMAND sparkinterval-tg-platt-windowed-core
            --terms=256 --stages=2 --blocks=1 --repetitions=1
            --reanchor-blocks=1 --fft-passes=0 --source-geometry
            --gamma-synthesis
  )
  add_test(
    NAME tg_platt_windowed_dd_source_stream_smoke
    COMMAND sparkinterval-tg-platt-windowed-core
            --terms=256 --stages=2 --blocks=1 --repetitions=1
            --fft-passes=0 --source-geometry --dd-source-blocks=2
  )
endif()
if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_SEMANTIC)
  add_test(
    NAME tg_platt_event_scan_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_EVENT_SCAN_BENCHMARK=$<TARGET_FILE:sparkinterval-tg-platt-event-scan-benchmark>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_event_scan
  )
  set_tests_properties(
    tg_platt_event_scan_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;event;three-stream;cuda;known-answer"
  )
  add_test(
    NAME tg_platt_pt21_event_record_known_answers
    COMMAND ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_pt21_event_record
  )
  set_tests_properties(
    tg_platt_pt21_event_record_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;event;compact-wire;known-answer"
  )
  add_test(
    NAME tg_platt_dd_transform_device_api_smoke
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DD_TRANSFORM_API_SMOKE=$<TARGET_FILE:sparkinterval-tg-platt-dd-transform-api-smoke>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_dd_transform_api
  )
  set_tests_properties(tg_platt_dd_transform_device_api_smoke PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;semantic;disk;cuda;device-api;attack;slow"
  )
  add_test(
    NAME tg_platt_dd_tile9_qualification_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DD_TILE9_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-dd-tile9-qualification>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_dd_tile9_qualification
  )
  set_tests_properties(
    tg_platt_dd_tile9_qualification_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;dd;fft;tile9;qualification;known-answer;slow"
  )
  add_test(
    NAME tg_platt_dd_sloppy_mul_qualification_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DD_SLOPPY_MUL_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-dd-sloppy-mul-qualification>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_dd_sloppy_mul_qualification
  )
  set_tests_properties(
    tg_platt_dd_sloppy_mul_qualification_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;dd;sloppy-mul;qualification;exact-dyadic;known-answer"
  )
  add_test(
    NAME tg_platt_dd_sloppy_root_whole_transform_qualification_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DD_SLOPPY_ROOT_WHOLE_TRANSFORM_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-dd-sloppy-root-whole-transform-qualification>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_dd_sloppy_root_whole_transform_qualification
  )
  set_tests_properties(
    tg_platt_dd_sloppy_root_whole_transform_qualification_known_answers
    PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;dd;sloppy-root;whole-transform;qualification;exact-dyadic;slow"
  )
  add_test(
    NAME tg_platt_dd_tile9_sloppy_root_whole_transform_qualification_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DD_TILE9_SLOPPY_ROOT_WHOLE_TRANSFORM_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-dd-tile9-sloppy-root-whole-transform-qualification>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_dd_tile9_sloppy_root_whole_transform_qualification
  )
  set_tests_properties(
    tg_platt_dd_tile9_sloppy_root_whole_transform_qualification_known_answers
    PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;dd;tile9;sloppy-root;whole-transform;qualification;exact-dyadic;slow"
  )
  if(TARGET sparkinterval-tg-platt-pt21-live-transform-candidate-qualification)
    add_test(
      NAME tg_platt_pt21_live_transform_candidate_qualification_known_answers
      COMMAND ${CMAKE_COMMAND} -E env
              TG_PLATT_PT21_LIVE_TRANSFORM_CANDIDATE_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-pt21-live-transform-candidate-qualification>
              ${Python3_EXECUTABLE} -m unittest -v
              tests.test_tg_platt_pt21_live_transform_candidate_qualification
    )
    set_tests_properties(
      tg_platt_pt21_live_transform_candidate_qualification_known_answers
      PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      LABELS "tg;platt;dd;live-v2;tile9;sloppy-root;qualification;exact-dyadic;slow"
    )
  endif()
  if(TARGET sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification)
    add_test(
      NAME tg_platt_pt21_bitreverse_tile9_qualification_known_answers
      COMMAND ${CMAKE_COMMAND} -E env
              TG_PLATT_PT21_BITREVERSE_TILE9_QUALIFICATION=$<TARGET_FILE:sparkinterval-tg-platt-pt21-bitreverse-tile9-qualification>
              ${Python3_EXECUTABLE} -m unittest -v
              tests.test_tg_platt_pt21_bitreverse_tile9_qualification
    )
    set_tests_properties(
      tg_platt_pt21_bitreverse_tile9_qualification_known_answers
      PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      LABELS "tg;platt;dd;live-v2;bitreverse;tile9;sloppy-root;qualification;exact-dyadic;slow"
    )
  endif()
  if(TARGET sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification)
    add_test(
      NAME tg_platt_pt21_multiwindow_reuse_bounds_known_answers
      COMMAND ${CMAKE_COMMAND} -E env
              TG_PLATT_PT21_MULTIWINDOW_REUSE=$<TARGET_FILE:sparkinterval-tg-platt-pt21-multiwindow-reuse-qualification>
              ${Python3_EXECUTABLE} -m unittest
              tests.test_tg_platt_pt21_multiwindow_reuse
    )
    set_tests_properties(
      tg_platt_pt21_multiwindow_reuse_bounds_known_answers PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      LABELS "tg;platt;multiwindow;qualification;bounds;known-answer"
    )
  endif()
  if(TARGET sparkinterval-tg-platt-pt21-recentered-pipeline-qualification)
    add_test(
      NAME tg_platt_pt21_recentered_pipeline_known_answers
      COMMAND ${CMAKE_COMMAND} -E env
              TG_PLATT_PT21_RECENTERED_PIPELINE=$<TARGET_FILE:sparkinterval-tg-platt-pt21-recentered-pipeline-qualification>
              ${Python3_EXECUTABLE} -m unittest
              tests.test_tg_platt_pt21_recentered_pipeline
    )
    set_tests_properties(
      tg_platt_pt21_recentered_pipeline_known_answers PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      LABELS "tg;platt;recentered;pipeline;qualification;known-answer"
    )
  endif()
  add_test(
    NAME tg_platt_windowed_semantic_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_platt_windowed_semantic_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-platt-windowed-semantic>
  )
  set_tests_properties(tg_platt_windowed_semantic_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;semantic;cuda;known-answer"
  )
  add_test(
    NAME tg_platt_windowed_disk_semantic_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_DISK_BINARY=$<TARGET_FILE:sparkinterval-tg-platt-windowed-disk-semantic>
            TG_PLATT_DD_DISK_BINARY=$<TARGET_FILE:sparkinterval-tg-platt-windowed-dd-disk-semantic>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_disk_endpoint_certificate
            tests.test_tg_platt_windowed_disk_semantic
            tests.test_tg_platt_windowed_dd_disk_semantic
            tests.test_tg_platt_required_sign_packet
            tests.test_tg_platt_h100_campaign
  )
  set_tests_properties(
    tg_platt_windowed_disk_semantic_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;semantic;disk;cuda;known-answer"
  )
endif()
if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  add_test(
    NAME tg_platt_gamma_taylor_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_platt_gamma_taylor_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
  )
  set_tests_properties(tg_platt_gamma_taylor_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
  add_test(
    NAME tg_platt_gamma_taylor_stream_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            SPARKINTERVAL_TG_PLATT_GAMMA_TAYLOR_RUNNER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_gamma_taylor_stream
  )
  set_tests_properties(tg_platt_gamma_taylor_stream_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;gamma;stream;known-answer"
  )
  add_test(
    NAME tg_platt_stationary_resolver_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            PYTHONPATH=${CMAKE_SOURCE_DIR}
            TG_PLATT_STATIONARY_RESOLVER=$<TARGET_FILE:sparkinterval-tg-platt-stationary-resolver>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_stationary_resolver
  )
  set_tests_properties(
    tg_platt_stationary_resolver_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;stationary;flint;fallback;known-answer"
  )
  if(TARGET sparkinterval-tg-platt-stationary-junction-benchmark)
    add_test(
      NAME tg_platt_stationary_junction_known_answers
      COMMAND ${CMAKE_COMMAND} -E env
              PYTHONPATH=${CMAKE_SOURCE_DIR}
              TG_PLATT_STATIONARY_JUNCTION=$<TARGET_FILE:sparkinterval-tg-platt-stationary-junction-benchmark>
              ${Python3_EXECUTABLE} -m unittest -v
              tests.test_tg_platt_stationary_junction
    )
    set_tests_properties(
      tg_platt_stationary_junction_known_answers PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      LABELS "tg;platt;stationary;junction;cuda;flint;known-answer"
    )
    if(TARGET sparkinterval-tg-platt-inline-stationary-kat)
      add_test(
        NAME tg_platt_inline_stationary_known_answers
        COMMAND ${CMAKE_COMMAND} -E env
                PYTHONPATH=${CMAKE_SOURCE_DIR}
                TG_PLATT_INLINE_STATIONARY_KAT=$<TARGET_FILE:sparkinterval-tg-platt-inline-stationary-kat>
                TG_PLATT_STATIONARY_JUNCTION=$<TARGET_FILE:sparkinterval-tg-platt-stationary-junction-benchmark>
                ${Python3_EXECUTABLE} -m unittest -v
                tests.test_tg_platt_inline_stationary
      )
      set_tests_properties(
        tg_platt_inline_stationary_known_answers PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        LABELS "tg;platt;stationary;inline;cuda;flint;qualification;known-answer"
      )
    endif()
    if(TARGET sparkinterval-tg-platt-pt21-turing-inputs AND
       TARGET sparkinterval-tg-platt-pt21-native-finalizer)
      add_test(
        NAME tg_platt_pt21_bounded_block_chain_known_answers
        COMMAND ${CMAKE_COMMAND} -E env
                PYTHONPATH=${CMAKE_SOURCE_DIR}
                TG_PLATT_STATIONARY_JUNCTION=$<TARGET_FILE:sparkinterval-tg-platt-stationary-junction-benchmark>
                TG_PLATT_PT21_TURING_INPUTS=$<TARGET_FILE:sparkinterval-tg-platt-pt21-turing-inputs>
                TG_PLATT_PT21_NATIVE_FINALIZER=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-finalizer>
                TG_PLATT_FLINT_LIBRARY=${SPARKINTERVAL_FLINT_PLATT_LIBRARY}
                ${Python3_EXECUTABLE} -m unittest -v
                tests.test_tg_platt_pt21_bounded_block_chain
      )
      set_tests_properties(
        tg_platt_pt21_bounded_block_chain_known_answers PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        LABELS "tg;platt;stationary;turing;native;cuda;flint;known-answer"
      )
      add_test(
        NAME tg_platt_pt21_persistent_worker_known_answers
        COMMAND ${CMAKE_COMMAND} -E env
                PYTHONPATH=${CMAKE_SOURCE_DIR}
                TG_PLATT_STATIONARY_JUNCTION=$<TARGET_FILE:sparkinterval-tg-platt-stationary-junction-benchmark>
                TG_PLATT_PT21_TURING_INPUTS=$<TARGET_FILE:sparkinterval-tg-platt-pt21-turing-inputs>
                TG_PLATT_PT21_NATIVE_FINALIZER=$<TARGET_FILE:sparkinterval-tg-platt-pt21-native-finalizer>
                TG_PLATT_FLINT_LIBRARY=${SPARKINTERVAL_FLINT_PLATT_LIBRARY}
                ${Python3_EXECUTABLE} -m unittest -v
                tests.test_tg_platt_pt21_persistent_worker
      )
      set_tests_properties(
        tg_platt_pt21_persistent_worker_known_answers PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        LABELS "tg;platt;pt21;persistent;cuda;flint;arb;native;known-answer"
      )
    endif()
  endif()
  add_test(
    NAME tg_platt_pt21_turing_inputs_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            PYTHONPATH=${CMAKE_SOURCE_DIR}
            TG_PLATT_PT21_TURING_INPUTS=$<TARGET_FILE:sparkinterval-tg-platt-pt21-turing-inputs>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_pt21_turing_inputs
  )
  set_tests_properties(
    tg_platt_pt21_turing_inputs_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;turing;flint;source-inputs;known-answer"
  )
endif()
if(SPARKINTERVAL_BUILD_TG_PLATT_WINDOWED_CORE AND
   SPARKINTERVAL_FLINT_PLATT_ROOT)
  add_test(
    NAME tg_platt_gamma_stream_cpp_consumer_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            SPARKINTERVAL_TG_PLATT_GAMMA_TAYLOR_RUNNER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
            SPARKINTERVAL_TG_PLATT_GAMMA_STREAM_CONSUMER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-stream-consumer>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_gamma_stream_consumer
  )
  set_tests_properties(
    tg_platt_gamma_stream_cpp_consumer_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;gamma;stream;cpp;known-answer"
  )
  add_test(
    NAME tg_platt_gamma_stream_gpu_consumer_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_GAMMA_GPU_CONSUMER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-gpu-consumer>
            TG_PLATT_GAMMA_TAYLOR_PRODUCER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
            ${Python3_EXECUTABLE} -m unittest
            tests.test_tg_platt_gamma_stream_gpu_consumer
  )
  set_tests_properties(
    tg_platt_gamma_stream_gpu_consumer_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;gamma;stream;cuda;known-answer"
  )
  add_test(
    NAME tg_platt_gamma_v2_known_answers
    COMMAND ${CMAKE_COMMAND} -E env
            TG_PLATT_GAMMA_TAYLOR_V2_PRODUCER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor-v2>
            TG_PLATT_GAMMA_V2_GPU_CONSUMER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-v2-gpu-consumer>
            TG_PLATT_GAMMA_TAYLOR_PRODUCER=$<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
            ${Python3_EXECUTABLE} -m unittest -v
            tests.test_tg_platt_gamma_v2
  )
  set_tests_properties(
    tg_platt_gamma_v2_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tg;platt;gamma;stream;dd;cuda;full-row;known-answer"
  )
  add_test(
    NAME tg_platt_gamma_gpu_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_platt_gamma_gpu_known_answers.py
            --gpu-runner $<TARGET_FILE:sparkinterval-tg-platt-windowed-core>
            --gamma-runner $<TARGET_FILE:sparkinterval-tg-platt-gamma-taylor>
  )
  set_tests_properties(tg_platt_gamma_gpu_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_HURST_MERTENS_ROOT)
  add_test(
    NAME tg_hurst_residual_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_hurst_residual_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-hurst-residual-shard>
  )
  set_tests_properties(tg_hurst_residual_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_PSI_PRIMESIEVE_ROOT)
  add_test(
    NAME tg_psi_residual_shard_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_psi_residual_shard_known_answers.py
            --runner $<TARGET_FILE:sparkinterval-tg-psi-residual-shard>
  )
  set_tests_properties(tg_psi_residual_shard_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
  add_test(
    NAME tg_psi_affine_guard_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_psi_affine_guard_known_answers.py
            --affine-runner
            $<TARGET_FILE:sparkinterval-tg-psi-affine-guard-shard>
            --two-pass-runner
            $<TARGET_FILE:sparkinterval-tg-psi-residual-shard>
  )
  set_tests_properties(tg_psi_affine_guard_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
if(SPARKINTERVAL_FLINT_PLATT_ROOT)
  add_test(
    NAME tg_platt_zeta_shard_known_answers
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/tg_platt_zeta_shard_known_answers.py
            $<TARGET_FILE:sparkinterval-tg-platt-zeta-shard>
  )
  set_tests_properties(tg_platt_zeta_shard_known_answers PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
add_test(NAME dgx_spark_probe COMMAND sparkinterval-probe)
add_test(
  NAME dgx_spark_primitive_conformance
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tools/run_primitive_conformance.py
          --executable $<TARGET_FILE:sparkinterval-interval-batch>
          --count 1024
)
set_tests_properties(dgx_spark_primitive_conformance PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
if(SPARKINTERVAL_BUILD_H100_NATIVE)
  # This build cross-compiles the target-neutral prototype for H100 even when
  # configuration occurs on the DGX Spark.  Its lexical audit must therefore
  # bind sm_90.  Physical sm_90 conformance remains in
  # tools/run_h100_native_validation.sh, which refuses a non-H100 device.
  set(SPARKINTERVAL_EXPRESSION_AUDIT_TARGET sm_90)
else()
  set(SPARKINTERVAL_EXPRESSION_AUDIT_TARGET sm_121)
endif()
add_test(
  NAME dgx_spark_expression_ptx_audit
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tools/inspect_expression_ptx.py
          $<TARGET_FILE:sparkinterval-expression-batch>
          ${CMAKE_BINARY_DIR}/expression-ptx-audit.json
          --binary
          --target ${SPARKINTERVAL_EXPRESSION_AUDIT_TARGET}
)
set_tests_properties(dgx_spark_expression_ptx_audit PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
if(NOT SPARKINTERVAL_BUILD_H100_NATIVE)
  add_test(
    NAME dgx_spark_expression_conformance
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tools/run_expression_conformance.py
            --executable $<TARGET_FILE:sparkinterval-expression-batch>
            --count 1024
            --program-count 4
  )
  set_tests_properties(dgx_spark_expression_conformance PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()
add_test(
  NAME dgx_spark_generated_ptx_conformance
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tools/run_generated_ptx_conformance.py
          --generator ${CMAKE_SOURCE_DIR}/.lake/build/bin/sparkinterval-gen
          --driver $<TARGET_FILE:sparkinterval-generated-driver>
          --count 1024
)
set_tests_properties(dgx_spark_generated_ptx_conformance PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
