/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file textureTable.cxx
 * @author rbroderi
 * @date 2026-11-02
 */

#include "textureTable.h"

TypeHandle TextureTable::_type_handle;

/**
 * Creates an empty table.
 */
TextureTable::
TextureTable(const std::string &name) :
  ShaderBuffer(name, 0, GeomEnums::UH_dynamic)
{
}

/**
 * Adds a texture, sampled with its default sampler, and returns its index.
 */
int TextureTable::
add_texture(Texture *texture) {
  nassertr(texture != nullptr, -1);
  return add_texture(texture, texture->get_default_sampler());
}

/**
 * Adds a texture, sampled with the given sampler, and returns its index.
 */
int TextureTable::
add_texture(Texture *texture, const SamplerState &sampler) {
  nassertr(texture != nullptr, -1);

  LightMutexHolder holder(_lock);
  _entries.push_back({texture, sampler});
  ++_modified;
  return (int)_entries.size() - 1;
}

/**
 * Replaces the nth texture, sampled with its default sampler.
 */
void TextureTable::
set_texture(int n, Texture *texture) {
  nassertv(texture != nullptr);
  set_texture(n, texture, texture->get_default_sampler());
}

/**
 * Replaces the nth texture and its sampler.
 */
void TextureTable::
set_texture(int n, Texture *texture, const SamplerState &sampler) {
  nassertv(texture != nullptr);

  LightMutexHolder holder(_lock);
  nassertv(n >= 0 && (size_t)n < _entries.size());
  _entries[n]._texture = texture;
  _entries[n]._sampler = sampler;
  ++_modified;
  ++_rewritten;
}

/**
 * Removes every texture.
 */
void TextureTable::
clear() {
  LightMutexHolder holder(_lock);
  _entries.clear();
  ++_modified;
  ++_rewritten;
}

/**
 * Returns the number of textures.
 */
int TextureTable::
get_num_textures() const {
  LightMutexHolder holder(_lock);
  return (int)_entries.size();
}

/**
 * Returns the nth texture.
 */
PT(Texture) TextureTable::
get_texture(int n) const {
  LightMutexHolder holder(_lock);
  nassertr(n >= 0 && (size_t)n < _entries.size(), nullptr);
  return _entries[n]._texture;
}

/**
 * Returns the sampler the nth texture is sampled with.
 */
SamplerState TextureTable::
get_sampler(int n) const {
  LightMutexHolder holder(_lock);
  nassertr(n >= 0 && (size_t)n < _entries.size(), SamplerState());
  return _entries[n]._sampler;
}

/**
 * Returns the index of the first entry holding the given texture, or -1.
 */
int TextureTable::
find_texture(const Texture *texture) const {
  LightMutexHolder holder(_lock);
  for (size_t i = 0; i < _entries.size(); ++i) {
    if (_entries[i]._texture == texture) {
      return (int)i;
    }
  }
  return -1;
}

/**
 *
 */
void TextureTable::
output(std::ostream &out) const {
  LightMutexHolder holder(_lock);
  out << get_type() << " " << get_name() << ", " << _entries.size()
      << " textures";
}

/**
 * Copies the entries into the given vector, and returns the sequence that
 * changes with any change; rewritten is set to the one that changes only when
 * an entry was replaced or removed.  For the renderer.
 */
UpdateSeq TextureTable::
get_entries(pvector<Entry> &into, UpdateSeq &rewritten) const {
  LightMutexHolder holder(_lock);
  into = _entries;
  rewritten = _rewritten;
  return _modified;
}

/**
 * Returns the sequence that changes with any change to the table.
 */
UpdateSeq TextureTable::
get_modified() const {
  LightMutexHolder holder(_lock);
  return _modified;
}
