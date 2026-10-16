import { gpuTier, lowerQuality } from './device';

describe('gpuTier', () => {
  it('caps integrated and mobile GPUs at medium', () => {
    expect(gpuTier({ vendor: 'intel', architecture: 'gen-12lp' })).toBe('medium');
    expect(gpuTier({ renderer: 'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)' })).toBe('medium');
    expect(gpuTier({ vendor: 'amd', description: 'AMD Radeon(TM) Graphics' })).toBe('medium');
    expect(gpuTier({ vendor: 'qualcomm', architecture: 'adreno-7xx' })).toBe('medium');
  });

  it('leaves discrete GPUs at high', () => {
    expect(gpuTier({ vendor: 'nvidia', architecture: 'ampere' })).toBe('high');
    expect(gpuTier({ renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)' })).toBe('high');
    expect(gpuTier({ vendor: 'amd', architecture: 'rdna-3' })).toBe('high');
    expect(gpuTier({ vendor: 'apple', architecture: 'metal-3' })).toBe('high');
  });

  it('sends software renderers to low and says nothing when it knows nothing', () => {
    expect(gpuTier({ renderer: 'Google SwiftShader' })).toBe('low');
    expect(gpuTier({ vendor: 'intel', fallback: true })).toBe('low');
    expect(gpuTier({ vendor: '', description: '' })).toBeNull();
    expect(gpuTier(null)).toBeNull();
  });
});

describe('lowerQuality', () => {
  it('takes the lower tier and ignores a missing one', () => {
    expect(lowerQuality('high', 'medium')).toBe('medium');
    expect(lowerQuality('medium', 'high')).toBe('medium');
    expect(lowerQuality('low', 'high')).toBe('low');
    expect(lowerQuality('high', null)).toBe('high');
  });
});
