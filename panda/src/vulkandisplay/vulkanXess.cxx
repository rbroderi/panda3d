/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file vulkanXess.cxx
 * @author rbroderi
 * @date 2026-11-03
 */

#include "vulkanXess.h"
#include "vulkanTextureContext.h"
#include "xess/xess_vk.h"

#include <cmath>
#include <cstring>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN 1
#endif
#include <windows.h>
#endif

// Calls one of the library's entry points, which load() looked up.
#define XESS_CALL(name) ((decltype(&::name))_##name)

/**
 *
 */
VulkanXess::
~VulkanXess() {
#ifdef _WIN32
  if (_library != nullptr && !vulkan_process_exiting) {
    FreeLibrary((HMODULE)_library);
  }
#endif
}

/**
 * Loads the library (vulkan-xess-library) and looks up what is called.
 * Returns false, saying why once, if it is not there.
 */
bool VulkanXess::
load() {
  if (_library != nullptr) {
    return true;
  }
  if (_failed) {
    return false;
  }
#ifdef _WIN32
  Filename filename = vulkan_xess_library;
  std::wstring path = filename.to_os_specific_w();
  HMODULE module = LoadLibraryExW(path.c_str(), nullptr,
    filename.is_fully_qualified() ? LOAD_WITH_ALTERED_SEARCH_PATH : 0);
  if (module == nullptr) {
    vulkandisplay_cat.info()
      << "XeSS is not used: " << filename << " did not load.\n";
    _failed = true;
    return false;
  }
  void **slots[] = {
    &_xessGetVersion, &_xessVKGetRequiredDeviceExtensions,
    &_xessVKGetRequiredDeviceFeatures, &_xessVKCreateContext, &_xessVKInit,
    &_xessVKExecute, &_xessGetOptimalInputResolution, &_xessSetVelocityScale,
    &_xessDestroyContext,
  };
  const char *names[] = {
    "xessGetVersion", "xessVKGetRequiredDeviceExtensions",
    "xessVKGetRequiredDeviceFeatures", "xessVKCreateContext", "xessVKInit",
    "xessVKExecute", "xessGetOptimalInputResolution", "xessSetVelocityScale",
    "xessDestroyContext",
  };
  for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
    *slots[i] = (void *)GetProcAddress(module, names[i]);
    if (*slots[i] == nullptr) {
      vulkandisplay_cat.error()
        << "XeSS is not used: " << filename << " has no " << names[i] << ".\n";
      FreeLibrary(module);
      _failed = true;
      return false;
    }
  }
  _library = (void *)module;

  xess_version_t version = {};
  XESS_CALL(xessGetVersion)(&version);
  vulkandisplay_cat.info()
    << "Loaded XeSS " << version.major << "." << version.minor << "."
    << version.patch << " from " << filename << "\n";
  return true;
#else
  _failed = true;
  return false;
#endif
}

/**
 * Adds the device extensions XeSS needs to the given list (where not there
 * already), and sets the features it needs in the given chain, which must
 * hold the structures of the features it sets (Vulkan 1.2's, integer dot
 * product's and mutable descriptor type's), so that it does not add Vulkan
 * 1.3's beside the GSG's own.  Returns false if the device cannot run it.
 */
bool VulkanXess::
add_device_requirements(VkInstance instance, VkPhysicalDevice gpu,
                        std::vector<const char *> &extensions,
                        VkPhysicalDeviceFeatures2 *features) {
  uint32_t count = 0;
  const char *const *names = nullptr;
  xess_result_t result = XESS_CALL(xessVKGetRequiredDeviceExtensions)(
    instance, gpu, &count, &names);
  if (result != XESS_RESULT_SUCCESS) {
    vulkandisplay_cat.info()
      << "XeSS is not used: the device lacks extensions it needs ("
      << result << ").\n";
    return false;
  }

  // Which structures the chain starts with: XeSS must add none.
  pvector<const void *> before;
  for (VkBaseOutStructure *s = (VkBaseOutStructure *)features->pNext;
       s != nullptr; s = s->pNext) {
    before.push_back(s);
  }
  void *chain = features;
  result = XESS_CALL(xessVKGetRequiredDeviceFeatures)(instance, gpu, &chain);
  if (result != XESS_RESULT_SUCCESS || chain != (void *)features) {
    vulkandisplay_cat.info()
      << "XeSS is not used: the device lacks features it needs ("
      << result << ").\n";
    return false;
  }
  size_t i = 0;
  for (VkBaseOutStructure *s = (VkBaseOutStructure *)features->pNext;
       s != nullptr; s = s->pNext, ++i) {
    if (i >= before.size() || before[i] != s) {
      vulkandisplay_cat.error()
        << "XeSS is not used: it added a feature structure (" << s->sType
        << ") the GSG does not chain.\n";
      return false;
    }
  }

  for (uint32_t i = 0; i < count; ++i) {
    bool found = false;
    for (const char *name : extensions) {
      found = found || strcmp(name, names[i]) == 0;
    }
    if (!found) {
      extensions.push_back(names[i]);
    }
  }
  return true;
}

/**
 * Makes the context (the first time) and readies it for the given output and
 * input sizes, with the quality preset whose own input size is nearest the
 * given one.  Any work using the context must have finished.
 */
bool VulkanXess::
init(VkInstance instance, VkPhysicalDevice gpu, VkDevice device,
     const VkExtent3D &output, const LVecBase2i &input_size) {
  xess_result_t result;
  if (_context == nullptr) {
    xess_context_handle_t context = nullptr;
    result = XESS_CALL(xessVKCreateContext)(instance, gpu, device, &context);
    if (result != XESS_RESULT_SUCCESS) {
      vulkandisplay_cat.error()
        << "Failed to create the XeSS context (" << result << ").\n";
      return false;
    }
    _context = context;
  } else {
    vkDeviceWaitIdle(device);
  }

  static const xess_quality_settings_t presets[] = {
    XESS_QUALITY_SETTING_ULTRA_PERFORMANCE,
    XESS_QUALITY_SETTING_PERFORMANCE,
    XESS_QUALITY_SETTING_BALANCED,
    XESS_QUALITY_SETTING_QUALITY,
    XESS_QUALITY_SETTING_ULTRA_QUALITY,
    XESS_QUALITY_SETTING_ULTRA_QUALITY_PLUS,
    XESS_QUALITY_SETTING_AA,
  };
  xess_2d_t out = {output.width, output.height};
  xess_quality_settings_t quality = XESS_QUALITY_SETTING_QUALITY;
  double nearest = -1;
  for (xess_quality_settings_t preset : presets) {
    xess_2d_t optimal, least, most;
    if (XESS_CALL(xessGetOptimalInputResolution)(
          _context, &out, preset, &optimal, &least, &most) != XESS_RESULT_SUCCESS) {
      continue;
    }
    if ((uint32_t)input_size[0] < least.x || (uint32_t)input_size[0] > most.x ||
        (uint32_t)input_size[1] < least.y || (uint32_t)input_size[1] > most.y) {
      continue;
    }
    double off = std::fabs((double)optimal.x - input_size[0]) +
                 std::fabs((double)optimal.y - input_size[1]);
    if (nearest < 0 || off < nearest) {
      nearest = off;
      quality = preset;
    }
  }
  if (nearest < 0) {
    vulkandisplay_cat.error()
      << "XeSS cannot upscale " << input_size << " to " << out.x << "x"
      << out.y << ": no quality preset takes that size.\n";
    return false;
  }

  xess_vk_init_params_t init_params = {};
  init_params.outputResolution = out;
  init_params.qualitySetting = quality;
  init_params.initFlags = XESS_INIT_FLAG_NONE;
  result = XESS_CALL(xessVKInit)(_context, &init_params);
  if (result != XESS_RESULT_SUCCESS) {
    vulkandisplay_cat.error()
      << "Failed to initialize XeSS (" << result << ").\n";
    return false;
  }
  if (vulkandisplay_cat.is_debug()) {
    vulkandisplay_cat.debug()
      << "XeSS upscales " << input_size << " to " << out.x << "x" << out.y
      << " with quality preset " << quality << "\n";
  }
  _output_size = output;
  _input_size = input_size;
  return true;
}

/**
 * Returns the view of the given texture XeSS reads or writes.
 */
static xess_vk_image_view_info
view_info(VulkanTextureContext *tc) {
  xess_vk_image_view_info info = {};
  info.imageView = tc->get_image_view(0);
  info.image = tc->_image;
  info.subresourceRange = {tc->_aspect_mask, 0, 1, 0, 1};
  info.format = tc->_format;
  info.width = tc->_extent.width;
  info.height = tc->_extent.height;
  return info;
}

/**
 * Records the upscale into the given command buffer, the textures already in
 * the layouts XeSS expects (shader read only, and general for the output),
 * readied first where the sizes changed.  Returns false if it could not.
 */
bool VulkanXess::
execute(VkInstance instance, VkPhysicalDevice gpu, VkDevice device,
        VkCommandBuffer cmd, VulkanTextureContext *color,
        VulkanTextureContext *depth, VulkanTextureContext *motion,
        VulkanTextureContext *output, const LVecBase2i &input_size,
        const UpscaleNode::Params &params) {
  if (_failed) {
    return false;
  }
  const VkExtent3D &out = output->_extent;
  bool fresh = false;
  if (_context == nullptr || out.width != _output_size.width ||
      out.height != _output_size.height || input_size != _input_size) {
    if (!init(instance, gpu, device, out, input_size)) {
      _failed = true;
      return false;
    }
    fresh = true;
  }

  XESS_CALL(xessSetVelocityScale)(_context, params._motion_scale[0],
                                  params._motion_scale[1]);

  xess_vk_execute_params_t exec = {};
  exec.colorTexture = view_info(color);
  exec.velocityTexture = view_info(motion);
  exec.depthTexture = view_info(depth);
  exec.outputTexture = view_info(output);
  exec.jitterOffsetX = params._jitter[0];
  exec.jitterOffsetY = params._jitter[1];
  exec.exposureScale = params._exposure;
  exec.resetHistory = (params._reset || fresh) ? 1 : 0;
  exec.inputWidth = input_size[0];
  exec.inputHeight = input_size[1];
  xess_result_t result = XESS_CALL(xessVKExecute)(_context, cmd, &exec);
  if (result != XESS_RESULT_SUCCESS) {
    vulkandisplay_cat.error()
      << "XeSS failed to upscale (" << result << "); not upscaling again.\n";
    _failed = true;
    return false;
  }
  return true;
}

/**
 * Destroys the context, if one was made.  Any work using it must have
 * finished.
 */
void VulkanXess::
destroy(VkDevice device) {
  if (_context != nullptr) {
    XESS_CALL(xessDestroyContext)(_context);
    _context = nullptr;
  }
  _output_size = {0, 0, 0};
  _input_size = LVecBase2i(0, 0);
}
