/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file vulkanTextureContext.h
 * @author rdb
 * @date 2016-02-19
 */

#ifndef VULKANTEXTURECONTEXT_H
#define VULKANTEXTURECONTEXT_H

#include "config_vulkandisplay.h"
#include "textureContext.h"
#include "small_vector.h"
#include "vulkanMemoryPage.h"

class VulkanCommandBuffer;
class VulkanFrameData;

/**
 * Manages a Vulkan image and device memory.
 */
class EXPCL_VULKANDISPLAY VulkanTextureContext : public TextureContext {
public:
  INLINE VulkanTextureContext(PreparedGraphicsObjects *pgo, Texture *texture = nullptr);
  ~VulkanTextureContext() {};

  ALLOC_DELETED_CHAIN(VulkanTextureContext);

  bool needs_recreation() const;

  void release(VulkanFrameData &frame_data);
  void destroy_now(VkDevice device);

  INLINE VkImageView get_image_view(int view) const;
  INLINE VkBufferView get_buffer_view(int view) const;
  VkImageView get_layer_view(VkDevice device, uint32_t layer);

  INLINE void mark_read(uint64_t seq);
  INLINE void discard();

  void clear_color_image(VulkanCommandBuffer &cmd, const VkClearColorValue &value);
  void clear_depth_stencil_image(VulkanCommandBuffer &cmd, const VkClearDepthStencilValue &value);
  void clear_buffer(VulkanCommandBuffer &cmd, uint32_t fill);

public:
  VkFormat _format = VK_FORMAT_UNDEFINED;
  VkExtent3D _extent;
  int _mipmap_begin = 0, _mipmap_end = 1;
  uint32_t _mip_levels = 1;
  uint32_t _array_layers = 1;
  VkImageAspectFlags _aspect_mask = 0;
  bool _generate_mipmaps = false;

  // How the RAM image's texels differ from the image's.  Panda keeps colour
  // in BGR(A) order whatever the component type, so an RGB-ordered image
  // needs the first and third components swapped, and most GPUs lack
  // three-component formats, so RGB is stored as RGBA with an opaque alpha.
  // A T_float texture in a 16-bit format has 32-bit floats in RAM and half
  // floats in the image, as OpenGL converts them.  _num_components and
  // _component_width describe the RAM image; _alpha_one is 1 in its type.
  struct TexelConversion {
    bool _swap_rb = false;
    bool _pack_rgb = false;
    bool _float_to_half = false;
    int _num_components = 0;
    int _component_width = 1;
    uint32_t _alpha_one = 0;

    bool needs_conversion() const { return _swap_rb || _pack_rgb || _float_to_half; }
    size_t get_image_size(size_t ram_size) const;
    void convert(void *dest, const void *src, size_t ram_size, bool to_image) const;
  };
  TexelConversion _conversion;
  bool _supports_render_to_texture = false;

  // Just for debugging.  It's -1 if it's not a swapchain image.
  int _swapchain_index = -1;

  // Depending on whether it's a buffer texture or image texture, either the
  // image and image view or buffer and buffer view will be set.
  VkImage _image = VK_NULL_HANDLE;
  small_vector<VkImageView> _image_views;
  // Single-layer 2D views of a layered image (a cube map's faces), made as
  // they are rendered into; null where none has been made.
  small_vector<VkImageView> _layer_views;
  VkBuffer _buffer = VK_NULL_HANDLE;
  small_vector<VkBufferView> _buffer_views;
  VulkanMemoryBlock _block;

  // Sequence number of the last command buffer in which this was used.
  uint64_t _read_seq = 0;
  uint64_t _write_seq = 0;

  // Index of the barrier into the list of barriers of the _read_seq CB.
  bool _hoisted_barrier_exists = true;
  size_t _image_barrier_index = 0;
  size_t _buffer_barrier_index = 0;

  // The "current" layout and details of the last write
  VkImageLayout _layout = VK_IMAGE_LAYOUT_UNDEFINED;
  VkAccessFlags2 _write_access_mask = 0;
  VkPipelineStageFlags2 _write_stage_mask = 0;

  // Which stages we've already synchronized with the last write.
  VkPipelineStageFlags2 _read_stage_mask = 0;

  // If you're wondering why there is no _read_access_mask, read this:
  // https://github.com/KhronosGroup/Vulkan-Docs/issues/131

public:
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    TextureContext::init_type();
    register_type(_type_handle, "VulkanTextureContext",
                  TextureContext::get_class_type());
  }
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}

private:
  static TypeHandle _type_handle;
};

#include "vulkanTextureContext.I"

#endif  // VULKANTEXTURECONTEXT_H
