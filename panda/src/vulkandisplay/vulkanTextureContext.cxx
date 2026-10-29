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

  for (VkImageView layer_view : _layer_views) {
    if (layer_view != VK_NULL_HANDLE) {
      frame_data._pending_destroy_image_views.push_back(layer_view);
    }
  }
  _layer_views.clear();

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

  for (VkImageView layer_view : _layer_views) {
    if (layer_view != VK_NULL_HANDLE) {
      vkDestroyImageView(device, layer_view, nullptr);
    }
  }
  _layer_views.clear();

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
 * Returns a 2D view of one layer of the image (one face of a cube map), to
 * render into, making it the first time it is asked for.
 */
VkImageView VulkanTextureContext::
get_layer_view(VkDevice device, uint32_t layer) {
  nassertr(_image != VK_NULL_HANDLE && layer < _array_layers, VK_NULL_HANDLE);
  if (_layer_views.size() <= layer) {
    _layer_views.resize(_array_layers, VK_NULL_HANDLE);
  }
  if (_layer_views[layer] == VK_NULL_HANDLE) {
    VkImageViewCreateInfo view_info = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    view_info.image = _image;
    view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view_info.format = _format;
    view_info.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
    view_info.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
    view_info.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
    view_info.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
    view_info.subresourceRange.aspectMask = _aspect_mask;
    view_info.subresourceRange.baseMipLevel = 0;
    view_info.subresourceRange.levelCount = 1;
    view_info.subresourceRange.baseArrayLayer = layer;
    view_info.subresourceRange.layerCount = 1;

    VkResult err = vkCreateImageView(device, &view_info, nullptr, &_layer_views[layer]);
    if (err) {
      vulkandisplay_cat.error()
        << "Failed to create view of layer " << layer << " (error " << err << ")\n";
      _layer_views[layer] = VK_NULL_HANDLE;
    }
  }
  return _layer_views[layer];
}
