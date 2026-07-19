cmake_minimum_required(VERSION 3.28)

project(SparkInterval LANGUAGES CXX CUDA)

find_package(CUDAToolkit REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

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

add_executable(sparkinterval-generated-driver
  gpu/src/generated_ptx_driver.cpp
)
target_link_libraries(sparkinterval-generated-driver PRIVATE CUDA::cuda_driver)

enable_testing()
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
