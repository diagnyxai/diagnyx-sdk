/**
 * Diagnyx Prompt Management SDK for Node.js
 */

// Types
export interface PromptVariable {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  required?: boolean;
  default?: unknown;
  description?: string;
}

export interface RenderedPrompt {
  systemPrompt: string | null;
  userPrompt: string | null;
  assistantPrompt: string | null;
  model: string | null;
  provider: string | null;
  temperature: number | null;
  maxTokens: number | null;
  topP: number | null;
  frequencyPenalty: number | null;
  presencePenalty: number | null;
  stopSequences: string[];
  responseFormat: Record<string, unknown> | null;
  otherParams: Record<string, unknown>;
  versionId: string;
  version: number;
  templateId: string;
  templateSlug: string;
}

export interface PromptVersion {
  id: string;
  version: number;
  systemPrompt: string | null;
  userPromptTemplate: string | null;
  assistantPrompt: string | null;
  model: string | null;
  provider: string | null;
  temperature: number | null;
  maxTokens: number | null;
  variables: PromptVariable[];
  commitMessage: string | null;
  createdAt: string;
}

export interface PromptDeployment {
  id: string;
  environment: string;
  version: PromptVersion;
  deployedAt: string;
}

export interface PromptTemplate {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  tags: string[];
  versions: PromptVersion[];
  deployments: PromptDeployment[];
  createdAt: string;
  updatedAt: string;
}

export interface GetPromptOptions {
  variables?: Record<string, unknown>;
  environment?: 'production' | 'staging' | 'development';
  version?: number;
  useCache?: boolean;
}

export interface LogUsageOptions {
  requestId?: string;
  userId?: string;
  variables?: Record<string, unknown>;
  success?: boolean;
  errorMessage?: string;
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  experimentId?: string;
  variantId?: string;
  feedbackScore?: number;
  feedbackText?: string;
}

export interface ExperimentVariant {
  variantId: string;
  variantName: string;
  versionId: string;
  version: PromptVersion;
}

interface CacheEntry {
  prompt: RenderedPrompt;
  timestamp: number;
}

/**
 * Helper class for working with rendered prompts
 */
export class PromptHelper {
  constructor(private readonly prompt: RenderedPrompt) {}

  /**
   * Convert to OpenAI messages format
   */
  toOpenAIMessages(userContent?: string): Array<{ role: string; content: string }> {
    const messages: Array<{ role: string; content: string }> = [];

    if (this.prompt.systemPrompt) {
      messages.push({ role: 'system', content: this.prompt.systemPrompt });
    }

    if (userContent) {
      messages.push({ role: 'user', content: userContent });
    } else if (this.prompt.userPrompt) {
      messages.push({ role: 'user', content: this.prompt.userPrompt });
    }

    if (this.prompt.assistantPrompt) {
      messages.push({ role: 'assistant', content: this.prompt.assistantPrompt });
    }

    return messages;
  }

  /**
   * Convert to Anthropic messages format
   */
  toAnthropicMessages(
    userContent?: string,
  ): { system: string | undefined; messages: Array<{ role: string; content: string }> } {
    const messages: Array<{ role: string; content: string }> = [];

    if (userContent) {
      messages.push({ role: 'user', content: userContent });
    } else if (this.prompt.userPrompt) {
      messages.push({ role: 'user', content: this.prompt.userPrompt });
    }

    if (this.prompt.assistantPrompt) {
      messages.push({ role: 'assistant', content: this.prompt.assistantPrompt });
    }

    return {
      system: this.prompt.systemPrompt || undefined,
      messages,
    };
  }

  /**
   * Get model configuration parameters
   */
  getModelParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {};

    if (this.prompt.model) params.model = this.prompt.model;
    if (this.prompt.temperature !== null) params.temperature = this.prompt.temperature;
    if (this.prompt.maxTokens !== null) params.max_tokens = this.prompt.maxTokens;
    if (this.prompt.topP !== null) params.top_p = this.prompt.topP;
    if (this.prompt.frequencyPenalty !== null)
      params.frequency_penalty = this.prompt.frequencyPenalty;
    if (this.prompt.presencePenalty !== null)
      params.presence_penalty = this.prompt.presencePenalty;
    if (this.prompt.stopSequences.length > 0) params.stop = this.prompt.stopSequences;
    if (this.prompt.responseFormat) params.response_format = this.prompt.responseFormat;

    return { ...params, ...this.prompt.otherParams };
  }
}

/**
 * Client for managing prompts with Diagnyx
 */
export class PromptsClient {
  private readonly cache: Map<string, CacheEntry> = new Map();
  private readonly cacheTtl = 300000; // 5 minutes in ms

  constructor(
    private readonly apiKey: string,
    private readonly organizationId: string,
    private readonly baseUrl: string = 'https://api.diagnyx.io',
    private readonly maxRetries: number = 3,
    private readonly debug: boolean = false,
  ) {}

  /**
   * Get and render a prompt template
   *
   * @example
   * ```typescript
   * const prompt = await dx.prompts(orgId).get('summarize-article', {
   *   variables: { article: articleText, maxWords: 100 },
   *   environment: 'production',
   * });
   *
   * const helper = new PromptHelper(prompt);
   * const response = await openai.chat.completions.create({
   *   model: prompt.model || 'gpt-4',
   *   messages: helper.toOpenAIMessages(),
   *   ...helper.getModelParams(),
   * });
   * ```
   */
  async get(slug: string, options: GetPromptOptions = {}): Promise<RenderedPrompt> {
    const { variables, environment, version, useCache = true } = options;
    const cacheKey = `${slug}:${environment || ''}:${version || ''}`;

    // Check cache
    if (useCache) {
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.cacheTtl) {
        return cached.prompt;
      }
    }

    const payload: Record<string, unknown> = {
      variables: variables || {},
    };
    if (environment) payload.environment = environment;
    if (version) payload.version = version;

    const data = await this.request<RenderedPrompt>(
      'POST',
      `/api/v1/organizations/${this.organizationId}/prompts/${slug}/render`,
      payload,
    );

    // Cache the result
    this.cache.set(cacheKey, { prompt: data, timestamp: Date.now() });

    return data;
  }

  /**
   * List prompt templates
   */
  async list(options: {
    search?: string;
    tags?: string[];
    includeArchived?: boolean;
    page?: number;
    limit?: number;
  } = {}): Promise<{ data: PromptTemplate[]; pagination: { total: number; page: number; limit: number; totalPages: number } }> {
    const params = new URLSearchParams();

    if (options.search) params.set('search', options.search);
    if (options.tags?.length) params.set('tags', options.tags.join(','));
    if (options.includeArchived) params.set('includeArchived', 'true');
    if (options.page) params.set('page', String(options.page));
    if (options.limit) params.set('limit', String(options.limit));

    const queryString = params.toString();
    const path = `/api/v1/organizations/${this.organizationId}/prompts${queryString ? `?${queryString}` : ''}`;

    return this.request('GET', path);
  }

  /**
   * Get a prompt template with all versions and deployments
   */
  async getTemplate(slug: string): Promise<PromptTemplate> {
    return this.request(
      'GET',
      `/api/v1/organizations/${this.organizationId}/prompts/${slug}`,
    );
  }

  /**
   * Log prompt usage for analytics
   */
  async logUsage(
    slug: string,
    version: number,
    environment: 'production' | 'staging' | 'development',
    options: LogUsageOptions = {},
  ): Promise<void> {
    const payload: Record<string, unknown> = {
      environment,
      success: options.success ?? true,
    };

    if (options.variables) payload.variables = options.variables;
    if (options.latencyMs !== undefined) payload.latencyMs = options.latencyMs;
    if (options.inputTokens !== undefined) payload.inputTokens = options.inputTokens;
    if (options.outputTokens !== undefined) payload.outputTokens = options.outputTokens;
    if (options.costUsd !== undefined) payload.costUsd = options.costUsd;
    if (options.userId) payload.userId = options.userId;
    if (options.requestId) payload.requestId = options.requestId;
    if (options.experimentId) payload.experimentId = options.experimentId;
    if (options.variantId) payload.variantId = options.variantId;
    if (options.feedbackScore !== undefined) payload.feedbackScore = options.feedbackScore;
    if (options.feedbackText) payload.feedbackText = options.feedbackText;
    if (options.errorMessage) payload.errorMessage = options.errorMessage;

    await this.request(
      'POST',
      `/api/v1/organizations/${this.organizationId}/prompts/${slug}/versions/${version}/usage`,
      payload,
    );
  }

  /**
   * Select a variant for an A/B test experiment
   */
  async selectExperimentVariant(slug: string, experimentId: string): Promise<ExperimentVariant> {
    return this.request(
      'POST',
      `/api/v1/organizations/${this.organizationId}/prompts/${slug}/experiments/${experimentId}/select-variant`,
    );
  }

  /**
   * Record a conversion for an A/B test variant
   */
  async recordConversion(
    slug: string,
    experimentId: string,
    variantId: string,
    metrics?: { latencyMs?: number; tokens?: number; costUsd?: number },
  ): Promise<void> {
    await this.request(
      'POST',
      `/api/v1/organizations/${this.organizationId}/prompts/${slug}/experiments/${experimentId}/variants/${variantId}/convert`,
      metrics || {},
    );
  }

  /**
   * Clear the prompt cache
   */
  clearCache(slug?: string): void {
    if (slug) {
      for (const key of this.cache.keys()) {
        if (key.startsWith(`${slug}:`)) {
          this.cache.delete(key);
        }
      }
    } else {
      this.cache.clear();
    }
  }

  private async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown>,
  ): Promise<T> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: body ? JSON.stringify(body) : undefined,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return (await response.json()) as T;
      } catch (error) {
        lastError = error as Error;
        this.log(`Request attempt ${attempt + 1} failed: ${lastError.message}`);

        if (attempt < this.maxRetries - 1) {
          await new Promise((resolve) => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }
      }
    }

    throw lastError || new Error('Request failed');
  }

  private log(message: string): void {
    if (this.debug) {
      console.log(`[Diagnyx.prompts] ${message}`);
    }
  }
}
