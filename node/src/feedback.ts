/**
 * Feedback Module for Diagnyx Node.js SDK
 *
 * Provides methods for collecting end-user feedback on LLM responses.
 * Feedback is linked to traces for analysis and fine-tuning.
 *
 * @example
 * ```typescript
 * import { Diagnyx } from '@diagnyx/node';
 *
 * const diagnyx = new Diagnyx({ apiKey: 'dx_...' });
 * const feedback = diagnyx.feedback('org-123');
 *
 * // Submit thumbs up feedback
 * await feedback.thumbsUp('trace_123');
 *
 * // Submit rating feedback
 * await feedback.rating('trace_123', 4);
 *
 * // Submit text feedback with tags
 * await feedback.text('trace_123', 'Great response!', {
 *   tags: ['accurate', 'helpful'],
 * });
 *
 * // Submit correction for fine-tuning
 * await feedback.correction('trace_123', 'The correct answer is Paris.');
 * ```
 */

export type FeedbackType =
  | 'thumbs_up'
  | 'thumbs_down'
  | 'rating'
  | 'text'
  | 'correction'
  | 'flag';

export type FeedbackSentiment = 'positive' | 'negative' | 'neutral';

export interface FeedbackOptions {
  /** Optional span ID for specific span feedback */
  spanId?: string;
  /** Optional text comment */
  comment?: string;
  /** Tags for categorization */
  tags?: string[];
  /** Additional metadata */
  metadata?: Record<string, unknown>;
  /** Anonymized user identifier */
  userId?: string;
  /** Session identifier */
  sessionId?: string;
}

export interface Feedback {
  id: string;
  traceId: string;
  feedbackType: FeedbackType;
  sentiment: FeedbackSentiment;
  rating?: number;
  comment?: string;
  correction?: string;
  tags: string[];
  metadata: Record<string, unknown>;
  userId?: string;
  sessionId?: string;
  spanId?: string;
  createdAt: Date;
}

export interface FeedbackSummary {
  totalFeedback: number;
  positiveCount: number;
  negativeCount: number;
  neutralCount: number;
  positiveRate: number;
  averageRating: number;
  feedbackByType: Record<string, number>;
  feedbackByTag: Record<string, number>;
}

export interface ListFeedbackOptions {
  limit?: number;
  offset?: number;
  feedbackType?: FeedbackType;
  sentiment?: FeedbackSentiment;
  tag?: string;
  startDate?: Date;
  endDate?: Date;
}

export interface ListFeedbackResult {
  data: Feedback[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Client for submitting and managing user feedback.
 *
 * Feedback is linked to traces and can be used for:
 * - Monitoring user satisfaction
 * - Identifying problematic responses
 * - Collecting data for fine-tuning
 * - Quality assurance
 */
export class FeedbackClient {
  private apiKey: string;
  private baseUrl: string;
  private organizationId: string;
  private maxRetries: number;
  private debug: boolean;

  constructor(
    apiKey: string,
    organizationId: string,
    baseUrl: string = 'https://api.diagnyx.com',
    maxRetries: number = 3,
    debug: boolean = false
  ) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
    this.organizationId = organizationId;
    this.maxRetries = maxRetries;
    this.debug = debug;
  }

  /**
   * Submit positive thumbs up feedback
   */
  async thumbsUp(traceId: string, options: FeedbackOptions = {}): Promise<Feedback> {
    return this.submit({
      traceId,
      feedbackType: 'thumbs_up',
      ...options,
    });
  }

  /**
   * Submit negative thumbs down feedback
   */
  async thumbsDown(traceId: string, options: FeedbackOptions = {}): Promise<Feedback> {
    return this.submit({
      traceId,
      feedbackType: 'thumbs_down',
      ...options,
    });
  }

  /**
   * Submit a numeric rating (1-5 stars)
   */
  async rating(
    traceId: string,
    value: number,
    options: FeedbackOptions = {}
  ): Promise<Feedback> {
    if (value < 1 || value > 5) {
      throw new Error('Rating value must be between 1 and 5');
    }

    return this.submit({
      traceId,
      feedbackType: 'rating',
      rating: value,
      ...options,
    });
  }

  /**
   * Submit text feedback/comment
   */
  async text(
    traceId: string,
    comment: string,
    options: Omit<FeedbackOptions, 'comment'> = {}
  ): Promise<Feedback> {
    return this.submit({
      traceId,
      feedbackType: 'text',
      comment,
      ...options,
    });
  }

  /**
   * Submit a correction for the response
   *
   * Corrections are used for fine-tuning - they provide the "correct"
   * response that should have been generated.
   */
  async correction(
    traceId: string,
    correction: string,
    options: FeedbackOptions = {}
  ): Promise<Feedback> {
    return this.submit({
      traceId,
      feedbackType: 'correction',
      correction,
      ...options,
    });
  }

  /**
   * Flag a response for review
   *
   * Use this for responses that need human review (e.g., potentially
   * harmful content, policy violations, etc.)
   */
  async flag(traceId: string, reason?: string, options: FeedbackOptions = {}): Promise<Feedback> {
    return this.submit({
      traceId,
      feedbackType: 'flag',
      comment: reason,
      ...options,
    });
  }

  /**
   * Submit feedback to the API
   */
  private async submit(params: {
    traceId: string;
    feedbackType: FeedbackType;
    rating?: number;
    comment?: string;
    correction?: string;
    spanId?: string;
    tags?: string[];
    metadata?: Record<string, unknown>;
    userId?: string;
    sessionId?: string;
  }): Promise<Feedback> {
    const payload: Record<string, unknown> = {
      traceId: params.traceId,
      feedbackType: params.feedbackType,
    };

    if (params.spanId) payload.spanId = params.spanId;
    if (params.rating !== undefined) payload.rating = params.rating;
    if (params.comment) payload.comment = params.comment;
    if (params.correction) payload.correction = params.correction;
    if (params.tags) payload.tags = params.tags;
    if (params.metadata) payload.metadata = params.metadata;
    if (params.userId) payload.userId = params.userId;
    if (params.sessionId) payload.sessionId = params.sessionId;

    const response = await this.request('POST', '/api/v1/feedback', payload);

    return this.parseFeedbackResponse(response);
  }

  /**
   * List feedback with filters
   */
  async list(options: ListFeedbackOptions = {}): Promise<ListFeedbackResult> {
    const params = new URLSearchParams();

    if (options.limit) params.set('limit', String(options.limit));
    if (options.offset) params.set('offset', String(options.offset));
    if (options.feedbackType) params.set('feedbackType', options.feedbackType);
    if (options.sentiment) params.set('sentiment', options.sentiment);
    if (options.tag) params.set('tag', options.tag);
    if (options.startDate) params.set('startDate', options.startDate.toISOString());
    if (options.endDate) params.set('endDate', options.endDate.toISOString());

    const queryString = params.toString();
    const path = `/api/v1/organizations/${this.organizationId}/feedback${
      queryString ? `?${queryString}` : ''
    }`;

    const response = await this.request('GET', path);

    return {
      data: (response.data || []).map(this.parseFeedbackResponse.bind(this)),
      total: response.total || 0,
      limit: response.limit || options.limit || 50,
      offset: response.offset || options.offset || 0,
    };
  }

  /**
   * Get feedback summary/analytics
   */
  async getSummary(options: { startDate?: Date; endDate?: Date } = {}): Promise<FeedbackSummary> {
    const params = new URLSearchParams();

    if (options.startDate) params.set('startDate', options.startDate.toISOString());
    if (options.endDate) params.set('endDate', options.endDate.toISOString());

    const queryString = params.toString();
    const path = `/api/v1/organizations/${this.organizationId}/feedback/analytics${
      queryString ? `?${queryString}` : ''
    }`;

    const response = await this.request('GET', path);

    return {
      totalFeedback: response.totalFeedback || 0,
      positiveCount: response.positiveCount || 0,
      negativeCount: response.negativeCount || 0,
      neutralCount: response.neutralCount || 0,
      positiveRate: response.positiveRate || 0,
      averageRating: response.averageRating || 0,
      feedbackByType: response.feedbackByType || {},
      feedbackByTag: response.feedbackByTag || {},
    };
  }

  /**
   * Get feedback for a specific trace
   */
  async getForTrace(traceId: string): Promise<Feedback[]> {
    const path = `/api/v1/organizations/${this.organizationId}/feedback/trace/${traceId}`;
    const response = await this.request('GET', path);

    return (response || []).map(this.parseFeedbackResponse.bind(this));
  }

  private parseFeedbackResponse(data: Record<string, unknown>): Feedback {
    return {
      id: data.id as string,
      traceId: data.traceId as string,
      feedbackType: data.feedbackType as FeedbackType,
      sentiment: data.sentiment as FeedbackSentiment,
      rating: data.rating as number | undefined,
      comment: data.comment as string | undefined,
      correction: data.correction as string | undefined,
      tags: (data.tags as string[]) || [],
      metadata: (data.metadata as Record<string, unknown>) || {},
      userId: data.userId as string | undefined,
      sessionId: data.sessionId as string | undefined,
      spanId: data.spanId as string | undefined,
      createdAt: new Date(data.createdAt as string),
    };
  }

  private async request(
    method: string,
    path: string,
    body?: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const url = path.startsWith('/api/v1/feedback')
          ? `${this.baseUrl}${path}`
          : `${this.baseUrl}${path}`;

        const response = await fetch(url, {
          method,
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: body ? JSON.stringify(body) : undefined,
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        return (await response.json()) as Record<string, unknown>;
      } catch (error) {
        lastError = error as Error;
        this.log(`Attempt ${attempt + 1} failed:`, lastError.message);

        if (attempt < this.maxRetries - 1) {
          await this.sleep(Math.pow(2, attempt) * 1000);
        }
      }
    }

    throw lastError;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private log(...args: unknown[]): void {
    if (this.debug) {
      console.log('[Diagnyx Feedback]', ...args);
    }
  }
}
