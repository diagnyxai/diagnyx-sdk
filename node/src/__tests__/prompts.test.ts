import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PromptsClient, PromptHelper, RenderedPrompt } from '../prompts';

describe('PromptsClient', () => {
  let client: PromptsClient;
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  const mockPrompt: RenderedPrompt = {
    systemPrompt: 'You are a helpful assistant.',
    userPrompt: 'Hello, World!',
    assistantPrompt: null,
    model: 'gpt-4',
    provider: 'openai',
    temperature: 0.7,
    maxTokens: 1000,
    topP: null,
    frequencyPenalty: null,
    presencePenalty: null,
    stopSequences: [],
    responseFormat: null,
    otherParams: {},
    versionId: 'version-123',
    version: 1,
    templateId: 'template-123',
    templateSlug: 'test-prompt',
  };

  beforeEach(() => {
    client = new PromptsClient('test-api-key', 'org-123', 'https://api.test.com');
    fetchSpy = vi.spyOn(global, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    client.clearCache();
  });

  describe('get', () => {
    it('should fetch and return a rendered prompt', async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(mockPrompt), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.get('test-prompt', {
        variables: { name: 'World' },
        environment: 'production',
      });

      expect(result).toEqual(mockPrompt);
      expect(fetchSpy).toHaveBeenCalledWith(
        'https://api.test.com/api/v1/organizations/org-123/prompts/test-prompt/render',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-api-key',
          }),
        })
      );
    });

    it('should cache results', async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(mockPrompt), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      // First call
      await client.get('test-prompt', { environment: 'production' });
      // Second call should use cache
      await client.get('test-prompt', { environment: 'production' });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('should bypass cache when useCache is false', async () => {
      fetchSpy.mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(mockPrompt), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      );

      await client.get('test-prompt', { environment: 'production' });
      await client.get('test-prompt', { environment: 'production', useCache: false });

      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('should retry on failure', async () => {
      fetchSpy
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(
          new Response(JSON.stringify(mockPrompt), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        );

      const result = await client.get('test-prompt');

      expect(result).toEqual(mockPrompt);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('should throw after max retries', async () => {
      fetchSpy.mockRejectedValue(new Error('Network error'));

      await expect(client.get('test-prompt')).rejects.toThrow('Network error');
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });
  });

  describe('list', () => {
    it('should list prompts with pagination', async () => {
      const mockResponse = {
        data: [{ id: '1', slug: 'prompt-1', name: 'Prompt 1' }],
        pagination: { total: 1, page: 1, limit: 10, totalPages: 1 },
      };

      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.list({ page: 1, limit: 10 });

      expect(result.data).toHaveLength(1);
      expect(result.pagination.total).toBe(1);
    });

    it('should include search and tags in query', async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ data: [], pagination: {} }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.list({ search: 'test', tags: ['tag1', 'tag2'] });

      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('search=test'),
        expect.any(Object)
      );
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('tags=tag1%2Ctag2'),
        expect.any(Object)
      );
    });
  });

  describe('getTemplate', () => {
    it('should fetch template with versions and deployments', async () => {
      const mockTemplate = {
        id: 'template-123',
        slug: 'test-prompt',
        name: 'Test Prompt',
        versions: [{ id: 'v1', version: 1 }],
        deployments: [],
      };

      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(mockTemplate), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.getTemplate('test-prompt');

      expect(result.slug).toBe('test-prompt');
      expect(result.versions).toHaveLength(1);
    });
  });

  describe('logUsage', () => {
    it('should log usage with all options', async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.logUsage('test-prompt', 1, 'production', {
        latencyMs: 150,
        inputTokens: 100,
        outputTokens: 200,
        costUsd: 0.005,
        success: true,
      });

      expect(fetchSpy).toHaveBeenCalledWith(
        'https://api.test.com/api/v1/organizations/org-123/prompts/test-prompt/versions/1/usage',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"environment":"production"'),
        })
      );
    });
  });

  describe('selectExperimentVariant', () => {
    it('should select a variant', async () => {
      const mockVariant = {
        variantId: 'variant-123',
        variantName: 'Control',
        versionId: 'version-1',
        version: { id: 'version-1', version: 1 },
      };

      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(mockVariant), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.selectExperimentVariant('test-prompt', 'exp-123');

      expect(result.variantId).toBe('variant-123');
    });
  });

  describe('clearCache', () => {
    it('should clear all cache', async () => {
      fetchSpy.mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(mockPrompt), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      );

      await client.get('test-prompt');
      client.clearCache();
      await client.get('test-prompt');

      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('should clear cache for specific slug', async () => {
      fetchSpy.mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(mockPrompt), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      );

      await client.get('prompt-1');
      await client.get('prompt-2');
      client.clearCache('prompt-1');
      await client.get('prompt-1'); // Should fetch again
      await client.get('prompt-2'); // Should use cache

      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });
  });
});

describe('PromptHelper', () => {
  const mockPrompt: RenderedPrompt = {
    systemPrompt: 'You are a helpful assistant.',
    userPrompt: 'Hello, how are you?',
    assistantPrompt: 'I am doing well!',
    model: 'gpt-4',
    provider: 'openai',
    temperature: 0.7,
    maxTokens: 1000,
    topP: 0.9,
    frequencyPenalty: 0.1,
    presencePenalty: 0.1,
    stopSequences: ['END'],
    responseFormat: { type: 'json_object' },
    otherParams: { seed: 42 },
    versionId: 'version-123',
    version: 1,
    templateId: 'template-123',
    templateSlug: 'test-prompt',
  };

  describe('toOpenAIMessages', () => {
    it('should convert to OpenAI messages format', () => {
      const helper = new PromptHelper(mockPrompt);
      const messages = helper.toOpenAIMessages();

      expect(messages).toHaveLength(3);
      expect(messages[0]).toEqual({ role: 'system', content: 'You are a helpful assistant.' });
      expect(messages[1]).toEqual({ role: 'user', content: 'Hello, how are you?' });
      expect(messages[2]).toEqual({ role: 'assistant', content: 'I am doing well!' });
    });

    it('should use custom user content', () => {
      const helper = new PromptHelper(mockPrompt);
      const messages = helper.toOpenAIMessages('Custom message');

      expect(messages[1]).toEqual({ role: 'user', content: 'Custom message' });
    });

    it('should handle missing prompts', () => {
      const minimalPrompt = { ...mockPrompt, systemPrompt: null, assistantPrompt: null };
      const helper = new PromptHelper(minimalPrompt);
      const messages = helper.toOpenAIMessages();

      expect(messages).toHaveLength(1);
      expect(messages[0].role).toBe('user');
    });
  });

  describe('toAnthropicMessages', () => {
    it('should convert to Anthropic messages format', () => {
      const helper = new PromptHelper(mockPrompt);
      const { system, messages } = helper.toAnthropicMessages();

      expect(system).toBe('You are a helpful assistant.');
      expect(messages).toHaveLength(2);
      expect(messages[0]).toEqual({ role: 'user', content: 'Hello, how are you?' });
      expect(messages[1]).toEqual({ role: 'assistant', content: 'I am doing well!' });
    });

    it('should use custom user content', () => {
      const helper = new PromptHelper(mockPrompt);
      const { messages } = helper.toAnthropicMessages('Custom message');

      expect(messages[0]).toEqual({ role: 'user', content: 'Custom message' });
    });
  });

  describe('getModelParams', () => {
    it('should return all model parameters', () => {
      const helper = new PromptHelper(mockPrompt);
      const params = helper.getModelParams();

      expect(params.model).toBe('gpt-4');
      expect(params.temperature).toBe(0.7);
      expect(params.max_tokens).toBe(1000);
      expect(params.top_p).toBe(0.9);
      expect(params.frequency_penalty).toBe(0.1);
      expect(params.presence_penalty).toBe(0.1);
      expect(params.stop).toEqual(['END']);
      expect(params.response_format).toEqual({ type: 'json_object' });
      expect(params.seed).toBe(42); // From otherParams
    });

    it('should omit null values', () => {
      const minimalPrompt = {
        ...mockPrompt,
        topP: null,
        frequencyPenalty: null,
        presencePenalty: null,
        stopSequences: [],
        responseFormat: null,
        otherParams: {},
      };
      const helper = new PromptHelper(minimalPrompt);
      const params = helper.getModelParams();

      expect(params).not.toHaveProperty('top_p');
      expect(params).not.toHaveProperty('frequency_penalty');
      expect(params).not.toHaveProperty('stop');
    });
  });
});
