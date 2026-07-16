export function parseExpectedFilenames(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[，,]/)
        .map((filename) => filename.trim())
        .filter(Boolean),
    ),
  ];
}
