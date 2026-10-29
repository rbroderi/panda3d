/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file vulkanTextureContext.cxx
 * @author rdb
 * @date 2016-02-19
 */

#include "vulkanTextureContext.h"
#include "vulkanCommandBuffer.h"
#include "vulkanFrameData.h"

TypeHandle VulkanTextureContext::_type_handle;

/**
 * Returns true if the texture needs to be recreated because of a change to the
 * size or format.
 */
bool VulkanTextureContext::
needs_recreation() const {
  Texture *tex = get_texture();
  if (tex->get_render_to_texture() && !_supports_render_to_texture) {
    return true;
  }

  int num_views = tex->get_num_views();

  VkExtent3D extent;
  extent.width = tex->get_x_size();
  extent.height = tex->get_y_size();
  uint32_t arrayLayers;

  if (tex->get_texture_type() == Texture::TT_3d_texture) {
    extent.depth = tex->get_z_size();
    arrayLayers = 1;
  } else if (tex->get_texture_type() == Texture::TT_1d_texture_array) {
    extent.height = 1;
    extent.depth = 1;
    arrayLayers = tex->get_y_size();
  } else {
    extent.depth = 1;
    arrayLayers = tex->get_z_size();
  }
  arrayLayers *= num_views;

  //VkFormat format = get_image_format(tex);

  return (//format != _format ||
          extent.width != _extent.width ||
          extent.height != _extent.height ||
          extent.depth != _extent.depth ||
          arrayLayers != _array_layers ||
          (size_t)num_views != _image_views.size());
}

/**
 * Schedules the deletion of the image resources for the end of the frame.
 */
void VulkanTextureContext::
release(VulkanFrameData &frame_data) {
  if (_image != VK_NULL_HANDLE) {
    frame_data._pending_destroy_images.push_back(_image);

    if (vulkandisplay_cat.is_debug()) {
      std::ostream &out = vulkandisplay_cat.debug()
        << "Scheduling image " << _image;

      if (!_image_views.empty()) {
        out << " with views";
        for (VkImageView image_view : _image_views) {
          out << " " << image_view;
        }
      }

      out << " for deletion\n";
    }

    _image = VK_NULL_HANDLE;
  }

  if (!_image_views.empty()) {
    frame_data._pending_destroy_image_views.insert(
      frame_data._pending_destroy_image_views.end(),
      _image_views.begin(), _image_views.end());

    _image_views.clear();
  }

  if (_buffer != VK_NULL_HANDLE) {
    frame_data._pending_destroy_buffers.push_back(_buffer);

    if (vulkandisplay_cat.is_debug()) {
      std::ostream &out = vulkandisplay_cat.debug()
        << "Scheduling buffer " << _buffer;

      if (!_buffer_views.empty()) {
        out << " with views";
        for (VkBufferView buffer_view : _buffer_views) {
          out << " " << buffer_view;
        }
      }

      out << " for deletion\n";
    }

    _buffer = VK_NULL_HANDLE;
  }

  if (!_buffer_views.empty()) {
    frame_data._pending_destroy_buffer_views.insert(
      frame_data._pending_destroy_buffer_views.end(),
      _buffer_views.begin(), _buffer_views.end());

    _buffer_views.clear();
  }

  // Make sure that the memory remains untouched until the frame is over.
  frame_data._pending_free.push_back(std::move(_block));

  // The memory isn't free yet, but it can be reclaimed by the memory allocator
  // if really necessary by waiting until the frame queue is empty.
  update_data_size_bytes(0);

  _format = VK_FORMAT_UNDEFINED;
  _layout = VK_IMAGE_LAYOUT_UNDEFINED;
}

/**
 * Destroys the handles associated with this context immediately.
 */
void VulkanTextureContext::
destroy_now(VkDevice device) {
  for (VkImageView image_view : _image_views) {
    vkDestroyImageView(device, image_view, nullptr);
  }
  _image_views.clear();

  if (_image != VK_NULL_HANDLE) {
    vkDestroyImage(device, _image, nullptr);
    _image = VK_NULL_HANDLE;
  }

  for (VkBufferView buffer_view : _buffer_views) {
    vkDestroyBufferView(device, buffer_view, nullptr);
  }
  _buffer_views.clear();

  if (_buffer != VK_NULL_HANDLE) {
    vkDestroyBuffer(device, _buffer, nullptr);
    _buffer = VK_NULL_HANDLE;
  }

  update_data_size_bytes(0);

  _format = VK_FORMAT_UNDEFINED;
  _layout = VK_IMAGE_LAYOUT_UNDEFINED;
}

/**
 * Inserts commands to clear the image.
 */
void VulkanTextureContext::
clear_color_image(VulkanCommandBuffer &cmd, const VkClearColorValue &value) {
  nassertv(_aspect_mask == VK_IMAGE_ASPECT_COLOR_BIT);
  nassertv(_image != VK_NULL_HANDLE);

  // We're not interested in whatever was in here before.
  discard();

  cmd.add_barrier(this, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_PIPELINE_STAGE_2_TRANSFER_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT);
  cmd.flush_barriers();

  VkImageSubresourceRange range;
  range.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
  range.baseMipLevel = 0;
  range.levelCount = _mip_levels;
  range.baseArrayLayer = 0;
  range.layerCount = _array_layers;
  vkCmdClearColorImage(cmd, _image, _layout, &value, 1, &range);
}

/**
 * Inserts commands to clear the image.
 */
void VulkanTextureContext::
clear_depth_stencil_image(VulkanCommandBuffer &cmd, const VkClearDepthStencilValue &value) {
  nassertv(_aspect_mask != VK_IMAGE_ASPECT_COLOR_BIT);
  nassertv(_image != VK_NULL_HANDLE);

  // We're not interested in whatever was in here before.
  discard();

  cmd.add_barrier(this, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_PIPELINE_STAGE_2_TRANSFER_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT);
  cmd.flush_barriers();

  VkImageSubresourceRange range;
  range.aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
  range.baseMipLevel = 0;
  range.levelCount = _mip_levels;
  range.baseArrayLayer = 0;
  range.layerCount = _array_layers;
  vkCmdClearDepthStencilImage(cmd, _image, _layout, &value, 1, &range);
}

/**
 * Inserts commands to clear the image.
 */
void VulkanTextureContext::
clear_buffer(VulkanCommandBuffer &cmd, uint32_t fill) {
  nassertv(_buffer != VK_NULL_HANDLE);

  discard();
  cmd.add_barrier(this, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                  VK_PIPELINE_STAGE_2_TRANSFER_BIT, VK_ACCESS_2_TRANSFER_WRITE_BIT);

  vkCmdFillBuffer(cmd, _buffer, 0, VK_WHOLE_SIZE, fill);
}

/**
 * Returns how many bytes the image holds for a RAM image of ram_size bytes.
 */
size_t VulkanTextureContext::TexelConversion::
get_image_size(size_t ram_size) const {
  if (_float_to_half) {
    ram_size /= 2;
  }
  return _pack_rgb ? ram_size / 3 * 4 : ram_size;
}

/**
 * Converts the bits of a 32-bit float to those of a 16-bit one, rounding to
 * nearest even, as glTexImage does for a half-float internal format.
 */
static uint16_t
float_to_half(uint32_t f) {
  uint32_t sign = (f >> 16) & 0x8000;
  uint32_t exp = (f >> 23) & 0xff;
  uint32_t mant = f & 0x7fffff;
  if (exp == 0xff) {
    // Infinity or NaN; keep NaNs NaN.
    return (uint16_t)(sign | 0x7c00 | (mant ? 0x200 : 0));
  }
  int e = (int)exp - 127 + 15;
  if (e >= 0x1f) {
    return (uint16_t)(sign | 0x7c00);
  }
  if (e <= 0) {
    // Subnormal half, or zero.
    if (e < -10) {
      return (uint16_t)sign;
    }
    mant |= 0x800000;
    uint32_t shift = (uint32_t)(14 - e);
    uint32_t half = mant >> shift;
    uint32_t rest = mant & ((1u << shift) - 1);
    uint32_t halfway = 1u << (shift - 1);
    if (rest > halfway || (rest == halfway && (half & 1))) {
      ++half;
    }
    return (uint16_t)(sign | half);
  }
  uint32_t half = sign | ((uint32_t)e << 10) | (mant >> 13);
  uint32_t rest = mant & 0x1fff;
  if (rest > 0x1000 || (rest == 0x1000 && (half & 1))) {
    ++half;  // may carry into the exponent, which is still right
  }
  return (uint16_t)half;
}

/**
 * Converts the bits of a 16-bit float to those of a 32-bit one.
 */
static uint32_t
half_to_float(uint16_t h) {
  uint32_t sign = (uint32_t)(h & 0x8000) << 16;
  uint32_t exp = (h >> 10) & 0x1f;
  uint32_t mant = h & 0x3ff;
  if (exp == 0x1f) {
    return sign | 0x7f800000 | (mant << 13);
  }
  if (exp == 0) {
    if (mant == 0) {
      return sign;
    }
    // Subnormal half: normalize it.
    int e = -1;
    do {
      ++e;
      mant <<= 1;
    } while ((mant & 0x400) == 0);
    return sign | ((uint32_t)(127 - 15 - e) << 23) | ((mant & 0x3ff) << 13);
  }
  return sign | ((exp - 15 + 127) << 23) | (mant << 13);
}

/**
 * Copies texels between their RAM image layout and the image's, converting
 * each component with convert_component.  With to_image, src is the RAM
 * image and dest the image's memory; otherwise the other way round.
 */
template<class S, class D, class Convert>
static void
do_convert_texels(D *dest, const S *src, size_t num_texels,
                  const VulkanTextureContext::TexelConversion &conversion,
                  bool to_image, Convert convert_component) {
  int src_step = conversion._num_components;
  int dest_step = conversion._num_components;
  if (conversion._pack_rgb) {
    (to_image ? dest_step : src_step) = 4;
  }
  // The alpha added when packing, in the image's representation.
  D alpha_one = to_image ? convert_component((S)conversion._alpha_one) : (D)0;
  bool swap_rb = conversion._swap_rb;
  for (size_t i = 0; i < num_texels; ++i) {
    for (int c = 0; c < dest_step; ++c) {
      int sc = c;
      if (swap_rb && c == 0) {
        sc = 2;
      } else if (swap_rb && c == 2) {
        sc = 0;
      }
      dest[c] = (sc < src_step) ? convert_component(src[sc]) : alpha_one;
    }
    src += src_step;
    dest += dest_step;
  }
}

/**
 * Copies ram_size bytes' worth of texels between a RAM image and the image's
 * memory, converting them as this says (see the struct).
 */
void VulkanTextureContext::TexelConversion::
convert(void *dest, const void *src, size_t ram_size, bool to_image) const {
  nassertv(_num_components > 0 && _component_width > 0);
  nassertv(!_swap_rb || _num_components >= 3);
  size_t num_texels = ram_size / ((size_t)_num_components * _component_width);

  if (_float_to_half) {
    nassertv(_component_width == 4);
    if (to_image) {
      do_convert_texels((uint16_t *)dest, (const uint32_t *)src, num_texels,
                        *this, to_image, float_to_half);
    } else {
      do_convert_texels((uint32_t *)dest, (const uint16_t *)src, num_texels,
                        *this, to_image, half_to_float);
    }
    return;
  }

  switch (_component_width) {
  case 1:
    do_convert_texels((uint8_t *)dest, (const uint8_t *)src, num_texels,
                      *this, to_image, [](uint8_t v) { return v; });
    break;
  case 2:
    do_convert_texels((uint16_t *)dest, (const uint16_t *)src, num_texels,
                      *this, to_image, [](uint16_t v) { return v; });
    break;
  case 4:
    do_convert_texels((uint32_t *)dest, (const uint32_t *)src, num_texels,
                      *this, to_image, [](uint32_t v) { return v; });
    break;
  default:
    nassert_raise("unsupported component width for texel conversion");
  }
}
