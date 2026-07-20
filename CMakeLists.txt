cmake_minimum_required(VERSION 3.28)

project(SparkInterval LANGUAGES CXX CUDA)

find_package(CUDAToolkit REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

option(
  SPARKINTERVAL_BUILD_H100_NATIVE
  "Build native-host H100 runners and sm_90 device artifacts"
  OFF
)

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

  add_custom_target(sparkinterval-h100-native)
  add_dependencies(sparkinterval-h100-native
    sparkinterval-h100-probe-cubin
    sparkinterval-h100-probe-runner
    sparkinterval-h100-interval-batch
    sparkinterval-h100-expression-batch
  )
endif()

add_executable(sparkinterval-generated-driver
  gpu/src/generated_ptx_driver.cpp
)
target_include_directories(sparkinterval-generated-driver PRIVATE gpu/include)
target_link_libraries(sparkinterval-generated-driver PRIVATE CUDA::cuda_driver)

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

enable_testing()
if(SPARKINTERVAL_BUILD_H100_NATIVE)
  add_test(
    NAME h100_native_cli_offline
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/test_h100_native_cli.py
            --probe $<TARGET_FILE:sparkinterval-h100-probe-runner>
            --primitive $<TARGET_FILE:sparkinterval-h100-interval-batch>
            --expression $<TARGET_FILE:sparkinterval-h100-expression-batch>
            --probe-cubin ${SPARKINTERVAL_H100_PROBE_CUBIN}
            --cuobjdump ${SPARKINTERVAL_CUOBJDUMP}
  )
  set_tests_properties(h100_native_cli_offline PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
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
add_test(
  NAME dgx_spark_expression_ptx_audit
  COMMAND ${Python3_EXECUTABLE}
          ${CMAKE_SOURCE_DIR}/tools/inspect_expression_ptx.py
          $<TARGET_FILE:sparkinterval-expression-batch>
          ${CMAKE_BINARY_DIR}/expression-ptx-audit.json
          --binary
)
set_tests_properties(dgx_spark_expression_ptx_audit PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
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
