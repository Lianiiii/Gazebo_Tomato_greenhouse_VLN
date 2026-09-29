cmake_minimum_required(VERSION 3.8)
project(tomato_bot_description)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(xacro REQUIRED)

# Install URDF / xacro / launch / config
install(DIRECTORY
  launch
  urdf
  xacro
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
