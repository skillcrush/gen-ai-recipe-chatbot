-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create a table to store your recipes
create table
  recipes_v2 (
    id uuid primary key,
    content text, -- corresponds to Document.pageContent
    metadata jsonb, -- corresponds to Document.metadata
    embedding vector (1536) -- 1536 works for OpenAI embeddings, change if needed
  );

-- Create a function to search for recipes
create function match_recipes_v2 (
  query_embedding vector (1536),
  filter jsonb default '{}'
) returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
) language plpgsql as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (recipes_v2.embedding <=> query_embedding) as similarity
  from recipes_v2
  where metadata @> filter
  order by recipes_v2.embedding <=> query_embedding;
end;
$$
SET statement_timeout TO '360s';