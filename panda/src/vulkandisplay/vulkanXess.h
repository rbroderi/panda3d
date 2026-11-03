/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file vulkanXess.h
 * @author rbroderi
 * @date 2026-11-03
 */

#ifndef VULKANXESS_H
#define VULKANXESS_H

#include "config_vulkandisplay.h"
#include "upscaleNode.h"

#include <vector>

class VulkanTextureContext;
struct _xess_context_handle_t;

/**
 * Intel's XeSS Super Resolution, the Vulkan renderer's temporal upscaler for
 * an UpscaleNode.  Its library (vulkan-xess-library) is loaded at runtime,
 * and only its public headers (MIT, in xess/) are built in: where it does not
 * load, the GSG has no upscaler.  It runs on any GPU with the features it
 * asks for, through its cross-vendor path where the GPU is not Intel's.
 */
class VulkanXess {
public:
  VulkanXess() = default;
  ~VulkanXess();

  bool load();
  bool add_device_requirements(VkInstance instance, VkPhysicalDevice gpu,
                               std::vector<const char *> &extensions,
                               VkPhysicalDeviceFeatures2 *features);
  bool execute(VkInstance instance, VkPhysicalDevice gpu, VkDevice device,
               VkCommandBuffer cmd, VulkanTextureContext *color,
               VulkanTextureContext *depth, VulkanTextureContext *motion,
               VulkanTextureContext *output, const LVecBase2i &input_size,
               const UpscaleNode::Params &params);
  void destroy(VkDevice device);

private:
  bool init(VkInstance instance, VkPhysicalDevice gpu, VkDevice device,
            const VkExtent3D &output, const LVecBase2i &input_size);

  void *_library = nullptr;
  _xess_context_handle_t *_context = nullptr;
  VkExtent3D _output_size = {0, 0, 0};
  LVecBase2i _input_size = LVecBase2i(0, 0);
  bool _failed = false;

  // The library's entry points (decltype of xess_vk.h's declarations).
  void *_xessGetVersion = nullptr;
  void *_xessVKGetRequiredDeviceExtensions = nullptr;
  void *_xessVKGetRequiredDeviceFeatures = nullptr;
  void *_xessVKCreateContext = nullptr;
  void *_xessVKInit = nullptr;
  void *_xessVKExecute = nullptr;
  void *_xessGetOptimalInputResolution = nullptr;
  void *_xessSetVelocityScale = nullptr;
  void *_xessDestroyContext = nullptr;
};

#endif
