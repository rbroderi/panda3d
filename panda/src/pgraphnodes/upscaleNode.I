/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file upscaleNode.I
 * @author rbroderi
 * @date 2026-11-03
 */

/**
 * Sets the jittered color texture to upscale, linear.
 */
INLINE void UpscaleNode::
set_color(Texture *color) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._color = color;
}

/**
 * Returns the color texture to upscale.
 */
INLINE Texture *UpscaleNode::
get_color() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._color;
}

/**
 * Sets the color's depth texture: 0 near, 1 far.
 */
INLINE void UpscaleNode::
set_depth(Texture *depth) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._depth = depth;
}

/**
 * Returns the color's depth texture.
 */
INLINE Texture *UpscaleNode::
get_depth() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._depth;
}

/**
 * Sets the color's motion texture: from each texel to where it was the frame
 * before, times the motion scale in pixels.
 */
INLINE void UpscaleNode::
set_motion(Texture *motion) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._motion = motion;
}

/**
 * Returns the color's motion texture.
 */
INLINE Texture *UpscaleNode::
get_motion() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._motion;
}

/**
 * Sets the texture the upscaled picture is written to.
 */
INLINE void UpscaleNode::
set_output(Texture *output) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._output = output;
}

/**
 * Returns the texture the upscaled picture is written to.
 */
INLINE Texture *UpscaleNode::
get_output() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._output;
}

/**
 * Sets how much of the color, from its first texel, holds the frame; zero
 * (the default) for all of it.
 */
INLINE void UpscaleNode::
set_input_size(const LVecBase2i &size) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._input_size = size;
}

/**
 * Returns how much of the color holds the frame (zero: all of it).
 */
INLINE LVecBase2i UpscaleNode::
get_input_size() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._input_size;
}

/**
 * Sets this frame's jitter, in pixels of the color.
 */
INLINE void UpscaleNode::
set_jitter(const LVecBase2 &jitter) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._jitter = jitter;
}

/**
 * Returns this frame's jitter, in pixels of the color.
 */
INLINE LVecBase2 UpscaleNode::
get_jitter() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._jitter;
}

/**
 * Sets what the motion texture's values are multiplied by to be pixels of
 * the color: its size, for motion in texture coordinates.  1 by default.
 */
INLINE void UpscaleNode::
set_motion_scale(const LVecBase2 &scale) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._motion_scale = scale;
}

/**
 * Returns what the motion texture's values are multiplied by.
 */
INLINE LVecBase2 UpscaleNode::
get_motion_scale() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._motion_scale;
}

/**
 * Sets the exposure the color is seen with (the upscaler tone maps its blend
 * with it).  1 by default.
 */
INLINE void UpscaleNode::
set_exposure(PN_stdfloat exposure) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._exposure = exposure;
}

/**
 * Returns the exposure the color is seen with.
 */
INLINE PN_stdfloat UpscaleNode::
get_exposure() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._exposure;
}

/**
 * Sets whether this frame starts the picture afresh, its history dropped (a
 * cut, a jump).  It stays so until set false.
 */
INLINE void UpscaleNode::
set_reset(bool reset) {
  Upscaler::CDWriter cdata(_upscaler->_cycler);
  cdata->_params._reset = reset;
}

/**
 * Returns whether this frame starts the picture afresh.
 */
INLINE bool UpscaleNode::
get_reset() const {
  Upscaler::CDReader cdata(_upscaler->_cycler);
  return cdata->_params._reset;
}

/**
 */
INLINE UpscaleNode::Upscaler::CData::
CData() {
}

/**
 */
INLINE UpscaleNode::Upscaler::CData::
CData(const UpscaleNode::Upscaler::CData &copy) :
  _params(copy._params)
{
}
