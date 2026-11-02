export function endpoints(p, width) {
  return [[p.X, 0, p.Y], [p.U, width, p.V]];
}
export function changed(a, b, tolerance = 0.05) {
  return !a || ["X","Y","U","V"].some(k => Math.abs(a[k] - b[k]) > tolerance);
}
export function project(point, yaw, pitch) {
  const [x,y,z] = point;
  const horizontal = x * Math.cos(yaw) - y * Math.sin(yaw);
  const depth = x * Math.sin(yaw) + y * Math.cos(yaw);
  return [horizontal, -z * Math.cos(pitch) + depth * Math.sin(pitch)];
}
