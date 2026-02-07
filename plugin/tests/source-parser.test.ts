/**
 * Tests for Source Path Parsing and Link Generation
 */

describe('Source Path Parsing', () => {
  describe('Path Extraction', () => {
    it('should extract relative path from absolute vault path', () => {
      const vaultPath = '/Users/test/vault';
      const sourcePath = '/Users/test/vault/Notes/MyNote.md';

      let result = sourcePath;
      if (result.startsWith(vaultPath)) {
        result = result.substring(vaultPath.length);
        if (result.startsWith('/')) {
          result = result.substring(1);
        }
      }

      expect(result).toBe('Notes/MyNote.md');
    });

    it('should remove .md extension for display', () => {
      const source = 'Notes/MyNote.md';
      const displayPath = source.endsWith('.md')
        ? source.substring(0, source.length - 3)
        : source;

      expect(displayPath).toBe('Notes/MyNote');
    });

    it('should extract basename from path', () => {
      const path = 'folder/subfolder/note.md';
      const basename = path.split('/').pop() || path;

      expect(basename).toBe('note.md');
    });

    it('should handle paths without .md extension', () => {
      const source = 'Notes/MyNote';
      const fileWithMd = source.endsWith('.md') ? source : source + '.md';

      expect(fileWithMd).toBe('Notes/MyNote.md');
    });
  });

  describe('Score Indicators', () => {
    function getScoreIndicator(score: number): string {
      if (score >= 0.8) return '🟢';
      if (score >= 0.6) return '🟡';
      if (score >= 0.4) return '🟠';
      return '🔴';
    }

    it('should return green for high scores', () => {
      expect(getScoreIndicator(0.9)).toBe('🟢');
      expect(getScoreIndicator(0.8)).toBe('🟢');
    });

    it('should return yellow for medium-high scores', () => {
      expect(getScoreIndicator(0.7)).toBe('🟡');
      expect(getScoreIndicator(0.6)).toBe('🟡');
    });

    it('should return orange for medium-low scores', () => {
      expect(getScoreIndicator(0.5)).toBe('🟠');
      expect(getScoreIndicator(0.4)).toBe('🟠');
    });

    it('should return red for low scores', () => {
      expect(getScoreIndicator(0.3)).toBe('🔴');
      expect(getScoreIndicator(0.1)).toBe('🔴');
    });
  });

  describe('Source Deduplication', () => {
    it('should remove duplicate sources by path', () => {
      const sources = [
        { path: 'Note1', displayName: 'Note1', score: 0.9, exists: true },
        { path: 'Note2', displayName: 'Note2', score: 0.8, exists: true },
        { path: 'Note1', displayName: 'Note1', score: 0.7, exists: true }, // duplicate
        { path: 'Note3', displayName: 'Note3', score: 0.6, exists: true }
      ];

      const seen = new Set<string>();
      const unique = sources.filter(s => {
        if (seen.has(s.path)) return false;
        seen.add(s.path);
        return true;
      });

      expect(unique).toHaveLength(3);
      expect(unique.map(s => s.path)).toEqual(['Note1', 'Note2', 'Note3']);
    });

    it('should keep highest score when deduplicating', () => {
      const sources = [
        { path: 'Note1', displayName: 'Note1', score: 0.7, exists: true },
        { path: 'Note1', displayName: 'Note1', score: 0.9, exists: true },
      ];

      // Sort by score first, then deduplicate
      const sorted = sources.sort((a, b) => b.score - a.score);
      const seen = new Set<string>();
      const unique = sorted.filter(s => {
        if (seen.has(s.path)) return false;
        seen.add(s.path);
        return true;
      });

      expect(unique).toHaveLength(1);
      expect(unique[0].score).toBe(0.9);
    });
  });

  describe('Source Filtering', () => {
    it('should filter out non-existent sources', () => {
      const sources = [
        { path: 'Note1', exists: true, score: 0.9 },
        { path: 'Note2', exists: false, score: 0.8 },
        { path: 'Note3', exists: true, score: 0.7 }
      ];

      const filtered = sources.filter(s => s.exists !== false);

      expect(filtered).toHaveLength(2);
      expect(filtered.every(s => s.exists === true)).toBe(true);
    });

    it('should sort sources by score descending', () => {
      const sources = [
        { score: 0.5 },
        { score: 0.9 },
        { score: 0.3 },
        { score: 0.7 }
      ];

      const sorted = sources.sort((a, b) => b.score - a.score);

      expect(sorted.map(s => s.score)).toEqual([0.9, 0.7, 0.5, 0.3]);
    });
  });
});
