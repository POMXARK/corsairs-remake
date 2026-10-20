# CFF File Format — Корсары: Проклятье Дальних Моря (2000)

## Sources

- GitHub: https://github.com/AlexKimov/seadogs-file-formats
- Wiki: https://github.com/AlexKimov/seadogs-file-formats/wiki/CFF-File-Format-Rus
- Storm Engine (open source): https://github.com/storm-devs/storm-engine
- VK group: https://vk.com/seadogsrevisited

## File Structure

```
FILE_HEADER (44 bytes):
  0x00  FLOAT  OBJECT_ORIGIN.X   (bbox center / offset X)
  0x04  FLOAT  OBJECT_ORIGIN.Y
  0x08  FLOAT  OBJECT_ORIGIN.Z
  0x0C  FLOAT  OBJECT_SCALE.X    (bbox size X)
  0x10  FLOAT  OBJECT_SCALE.Y
  0x14  FLOAT  OBJECT_SCALE.Z
  0x18  UINT   TextureCount
  0x1C  UINT   MaterialCount
  0x20  UINT   LOD               (number of LOD models)
  0x24  UINT   SectionOffset     (BSP section offset, 0 if none)
  0x28  FLOAT  LODSwitchDistance

TEXTURES (variable):
  For each texture:
    UBYTE  Length
    char   FileName[Length]

MATERIALS (MaterialCount × variable):
  For each material:
    UINT   Unknown[9]            (36 bytes)
    UINT   Count                 (number of texture properties)
    For each property:
      UINT   TextureIndex
      FLOAT  Unknown
      UINT   Unknown[3]         (20 bytes per property)

LOD_MODELS (LOD × variable):
  For each LOD:
    UINT   MeshCount
    UINT   Zero                 (always 0)
    MESHES (MeshCount × variable):
      MESH_HEADER (44 bytes):
        0x00  FLOAT  MESH_ORIGIN.X
        0x04  FLOAT  MESH_ORIGIN.Y
        0x08  FLOAT  MESH_ORIGIN.Z
        0x0C  FLOAT  UVDelim
        0x10  FLOAT  Radius
        0x14  UINT   TextureIndex
        0x18  UINT   VertexCount
        0x1C  UINT   FaceCount
        0x20  UINT   Unknown       (always 1)
        0x24  UINT   AnimationKeyCount
        0x28  char   Name[4]       (mesh name, no null terminator)

      VERTEXES (VertexCount × 13 bytes):
        UINT16  X                (quantized position)
        UINT16  Y
        UINT16  Z
        UINT16  U                (quantized UV)
        UINT16  V
        UBYTE   R                (color, 0-127)
        UBYTE   G
        UBYTE   B

      FACES (FaceCount × 3 or 6 bytes):
        If VertexCount <= 256:
          UBYTE  I1, I2, I3      (3 bytes per triangle)
        Else:
          UINT16 I1, I2, I3      (6 bytes per triangle)

      ANIMATIONS (AnimationKeyCount × 28 bytes):
        FLOAT  Translation.X
        FLOAT  Translation.Y
        FLOAT  Translation.Z
        FLOAT  Rotation.X
        FLOAT  Rotation.Y
        FLOAT  Rotation.Z
        FLOAT  Frame             (frame number / time)

BSP_SECTION (if SectionOffset > 0):
  UINT   Type
  UINT   Count1
  UINT   Count2
  UINT   Count3
  UINT   DataSize
  ... (BSP tree data)
```

## Coordinate Conversion

```c
// Position: quantized uint16 → world float
float pos_x = OBJECT_ORIGIN.x + vertex.x * OBJECT_SCALE.x / 32767.0f;
float pos_y = OBJECT_ORIGIN.y + vertex.y * OBJECT_SCALE.y / 32767.0f;
float pos_z = OBJECT_ORIGIN.z + vertex.z * OBJECT_SCALE.z / 32767.0f;

// UV: quantized uint16 → float
float uv_u = vertex.u / UVDelim;
float uv_v = vertex.v / UVDelim;

// Color: uint8 → float (0-127 range)
float color_r = vertex.r / 127.0f;
float color_g = vertex.g / 127.0f;
float color_b = vertex.b / 127.0f;
```

## Tools

| Tool | Description |
|------|-------------|
| 010 Editor + CFF.bt | Binary template for visual inspection |
| Noesis + fmt_sd_cff_clf.py | View CFF models in Noesis Invader |
| 3dsMax cff_clf_import.zip | Import CFF/CLF models with animations into 3dsMax |
| storm-engine (GitHub) | Open-source engine source (GPL-3.0) |

## Related Formats

| Extension | Description |
|-----------|-------------|
| .cff | 3D model (Sea Dogs 2000) |
| .clf | 3D model intermediate format (float positions, per-face UVs) |
| .ani | Animated scene |
| .tf  | Texture (Sea Dogs 2000) |
| .def | Composite object definition (ships) |
| .idf | Object properties table |
| .sls | Yard/ship layout |
| .gm  | 3D model (Pirates of Caribbean 2003, Age of Pirates 2006) — RDF format |
| .tx  | Texture (Pirates of Caribbean 2003+) |
| .an  | Animation (Pirates of Caribbean 2003+) |
