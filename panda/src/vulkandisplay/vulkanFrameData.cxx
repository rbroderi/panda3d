/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file vulkanFrameData.cxx
 * @author rdb
 * @date 2023-06-14
 */

#include "vulkanFrameData.h"
#include "vulkanTextureContext.h"

/**
 *
 */
void VulkanFrameData::
finish_downloads(VkDevice device) {
  for (QueuedDownload &down : _download_queue) {
    PTA_uchar target = down._texture->modify_ram_image();
    size_t view_size = down._texture->get_ram_view_size();

    if (auto data = down._block.map()) {
      down._block.invalidate();
      // A row at a time: rendered images are upside down, and the texels
      // may need converting back to the RAM image's layout.
      const VulkanTextureContext::TexelConversion &conversion = down._conversion;
      size_t row_size = down._texture->get_x_size()
                      * down._texture->get_num_components()
                      * down._texture->get_component_width();
      size_t image_row_size = conversion.get_image_size(row_size);
      unsigned char *view = target.p() + view_size * down._view;
      unsigned char *dst = down._flip ? view + view_size - row_size : view;
      ptrdiff_t dst_step = down._flip ? -(ptrdiff_t)row_size : (ptrdiff_t)row_size;
      unsigned char *src = (unsigned char *)data;
      for (size_t row = 0; row < view_size / row_size; ++row) {
        if (conversion.needs_conversion()) {
          conversion.convert(dst, src, row_size, false);
        } else {
          memcpy(dst, src, row_size);
        }
        src += image_row_size;
        dst += dst_step;
      }
    } else {
      vulkandisplay_cat.error()
        << "Failed to map memory for RAM transfer.\n";
    }

    // We won't need this buffer any more.
    vkDestroyBuffer(device, down._buffer, nullptr);

    if (down._request != nullptr) {
      down._request->finish();
    }
  }
  _download_queue.clear();
}

/**
 *
 */
void VulkanFrameData::
replace_timer_query_pool(VkQueryPool new_pool, size_t new_size) {
  if (_timer_query_pool._pool != VK_NULL_HANDLE) {
    TimerQueryPool *prev_pool = new TimerQueryPool(std::move(_timer_query_pool));
    _timer_query_pool._prev = prev_pool;
  }
  _timer_query_pool._pool = new_pool;
  _timer_query_pool._pool_size = new_size;
  _timer_query_pool._offset = 0;
  _timer_query_pool._pstats_indices.clear();
}
