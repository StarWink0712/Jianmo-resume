export const MAX_AVATAR_UPLOAD_BYTES = 1_000_000;
export const AVATAR_ACCEPT = '.jpg,.jpeg,.png,image/jpeg,image/png';
export const AVATAR_HINT = '支持 JPG、JPEG、PNG，文件不超过 1 MB；无需固定尺寸或比例。图片仅发送到本机，并自动优化尺寸、清理元数据。';

export function avatarFileError(file) {
  if (!/\.(jpe?g|png)$/i.test(file.name || '')) return '请选择 JPG、JPEG 或 PNG 格式的图片。';
  if (!Number.isInteger(file.size) || file.size <= 0) return '图片文件为空或无法读取，请重新选择。';
  if (file.size > MAX_AVATAR_UPLOAD_BYTES) return '头像文件不能超过 1 MB。';
  // Browser MIME types can be empty; the backend verifies the decoded image format.
  return '';
}
