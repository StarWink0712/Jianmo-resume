export const CROP_WIDTH = 600;
export const CROP_HEIGHT = 800;
export const MAX_CROP_ZOOM = 4;
export const MAX_AVATAR_DECODE_PIXELS = 4096 * 4096;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function cropTransform({width, height, zoom = 1, rotation = 0, x = 0, y = 0}) {
  if (![width, height, zoom, rotation, x, y].every(Number.isFinite) || width <= 0 || height <= 0) {
    throw new Error('图片尺寸或裁剪参数无效。');
  }
  zoom = clamp(zoom, 1, MAX_CROP_ZOOM);
  rotation = ((rotation + 180) % 360 + 360) % 360 - 180;
  const angle = rotation * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
  // Inverse-rotate the crop corners to keep the entire rectangle inside the photo.
  const spanX = CROP_WIDTH * Math.abs(c) + CROP_HEIGHT * Math.abs(s);
  const spanY = CROP_WIDTH * Math.abs(s) + CROP_HEIGHT * Math.abs(c);
  const scale = Math.max(spanX / width, spanY / height) * zoom;
  const limitX = Math.max(0, (width * scale - spanX) / 2);
  const limitY = Math.max(0, (height * scale - spanY) / 2);
  const localX = clamp(x * c + y * s, -limitX, limitX);
  const localY = clamp(-x * s + y * c, -limitY, limitY);
  return {width, height, zoom, rotation, scale, x: localX * c - localY * s, y: localX * s + localY * c};
}

export function cropFrame(width, height) {
  const scale = Math.min(width * .78 / CROP_WIDTH, height * .90 / CROP_HEIGHT);
  return {x: (width - CROP_WIDTH * scale) / 2, y: (height - CROP_HEIGHT * scale) / 2,
    width: CROP_WIDTH * scale, height: CROP_HEIGHT * scale, scale};
}

export async function isAvatarImage(blob) {
  const bytes = new Uint8Array(await blob.slice(0, 8).arrayBuffer());
  return [137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => bytes[i] === value)
    || (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255);
}

export async function avatarDimensions(blob) {
  const data = new DataView(await blob.arrayBuffer());
  const checked = (width, height) => {
    if (!width || !height) throw new Error('图片尺寸无效，请选择另一张图片。');
    if (width * height > MAX_AVATAR_DECODE_PIXELS) throw new Error('图片解码后的像素占用过大，请压缩图片后重试。');
    return {width, height};
  };
  // Inspect dimensions before asking the browser to allocate the decoded bitmap.
  if (data.byteLength >= 24 && data.getUint32(0) === 0x89504e47 && data.getUint32(4) === 0x0d0a1a0a
      && data.getUint32(8) === 13 && data.getUint32(12) === 0x49484452) {
    return checked(data.getUint32(16), data.getUint32(20));
  }
  if (data.byteLength >= 4 && data.getUint16(0) === 0xffd8) {
    let offset = 2;
    while (offset + 3 < data.byteLength && data.getUint8(offset++) === 0xff) {
      while (offset < data.byteLength && data.getUint8(offset) === 0xff) offset++;
      if (offset >= data.byteLength) break;
      const marker = data.getUint8(offset++);
      if (marker === 0xda || marker === 0xd9 || offset + 2 > data.byteLength) break;
      const length = data.getUint16(offset);
      if (length < 2 || offset + length > data.byteLength) break;
      if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) {
        if (length < 8) break;
        return checked(data.getUint16(offset + 5), data.getUint16(offset + 3));
      }
      offset += length;
    }
  }
  throw new Error('图片无法读取，请选择有效的 JPG、JPEG 或 PNG 图片。');
}
