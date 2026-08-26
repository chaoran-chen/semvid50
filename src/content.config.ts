import { defineCollection } from 'astro:content';
import { z } from 'zod';
import { glob } from 'astro/loaders';

// Written by tools/import.py; validated so a bad import fails the build rather
// than rendering a page with no title.
const wiki = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/wiki' }),
  schema: z.object({
    id: z.string(),
    title: z.string().min(1),
  }),
});

export const collections = { wiki };
