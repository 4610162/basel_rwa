export function preprocessMathContent(content: string): string {
  let result = content.replace(
    /\\begin\{split\}([\s\S]*?)\\end\{split\}/g,
    (_, body) => {
      const fixedBody = body.replace(/=\s*&\s*/g, " &= ");
      return `\\begin{aligned}${fixedBody}\\end{aligned}`;
    }
  );

  result = result.replace(/\\left\{/g, "\\left\\{");
  result = result.replace(/\\right\}/g, "\\right\\}");

  const protectedBlocks: string[] = [];
  result = result.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
    protectedBlocks.push(match);
    return `\x00MATHBLOCK${protectedBlocks.length - 1}\x00`;
  });

  result = result.replace(
    /\\begin\{(aligned|align\*?|equation\*?|gather\*?)\}[\s\S]*?\\end\{\1\}/g,
    (match) => `\n$$\n${match}\n$$\n`
  );

  result = result.replace(
    /\x00MATHBLOCK(\d+)\x00/g,
    (_, index) => protectedBlocks[Number(index)]
  );

  const displayMathBlockCount = (result.match(/\$\$/g) || []).length;
  if (displayMathBlockCount % 2 !== 0) {
    result += "\n$$";
  }

  return result;
}
