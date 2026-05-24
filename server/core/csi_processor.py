import numpy as np
from scipy.signal import medfilt

class CSIProcessor:
    def __init__(self, num_subcarriers=64):
        self.num_subcarriers = num_subcarriers
        # Initialize an empty matrix to establish the static background baseline
        self.background_baseline = None
        self.calibration_frames = 0
        self.calibration_limit = 30  # Number of frames used to map the empty room

    def clean_phase_errors(self, raw_phase):
        """
        Applies linear phase correction to eliminate random sampling frequency offsets.
        """
        subcarrier_indices = np.arange(self.num_subcarriers)
        # Calculate slope and intercept using linear regression
        slope, intercept = np.polyfit(subcarrier_indices, raw_phase, 1)
        corrected_phase = raw_phase - (slope * subcarrier_indices + intercept)
        return corrected_phase

    def hampel_filter(self, data, window_size=5, n_sigmas=3):
        """
        Detects and removes high-frequency thermal spikes/outliers from the stream.
        """
        n = len(data)
        new_data = data.copy()
        k = window_size // 2
        
        for i in range(k, n - k):
            window = data[i - k : i + k + 1]
            median = np.median(window)
            # Median Absolute Deviation (MAD)
            mad = np.median(np.abs(window - median))
            threshold = n_sigmas * 1.4826 * mad
            
            if np.abs(data[i] - median) > threshold:
                new_data[i] = median
        return new_data

    def process_frame(self, raw_amplitude, raw_phase):
        """
        Main execution loop for incoming CSI packets.
        """
        # 1. Clean the signal phase matrix
        clean_phase = self.clean_phase_errors(raw_phase)
        
        # 2. Filter amplitude noise spikes
        clean_amplitude = self.hampel_filter(raw_amplitude)
        
        # Combine amplitude and corrected phase into a unified complex channel matrix
        csi_matrix = clean_amplitude * np.exp(1j * clean_phase)
        
        # 3. Handle Static Background Subtraction
        if self.background_baseline is None:
            self.background_baseline = np.abs(csi_matrix)
            return None
        
        if self.calibration_frames < self.calibration_limit:
            # Exponential moving average to lock down the room baseline profile
            self.background_baseline = (0.9 * self.background_baseline) + (0.1 * np.abs(csi_matrix))
            self.calibration_frames += 1
            print(f"📡 Calibrating room baseline... Frame {self.calibration_frames}/{self.calibration_limit}")
            return None
        
        # Subtract background noise to isolate dynamic, moving objects (humans)
        residual_signal = np.abs(np.abs(csi_matrix) - self.background_baseline)
        
        # 4. Synthesize X, Y, Z Coordinates (Simplified spatial mapping)
        # Extracts top peak variations across subcarriers to project space tracking
        idx = int(np.argmax(residual_signal))
        x_coord = float(np.sin(idx) * residual_signal[idx] * 2)
        y_coord = float(np.cos(idx) * residual_signal[idx] * 2)
        z_coord = float(np.abs(np.mean(residual_signal)) * 1.5)
        
        return {"x": round(x_coord, 2), "y": round(y_coord, 2), "z": round(z_coord, 2)}


# Execution test loop simulation
if __name__ == "__main__":
    processor = CSIProcessor()
    print("🚀 Mathematical Signal Pipeline Initialized.")
    
    # Run mock simulation data chunks to verify logic matrix handles data without crashing
    for frame in range(40):
        mock_amp = np.random.normal(30, 2, 64)
        mock_phase = np.random.uniform(-np.pi, np.pi, 64)
        
        output = processor.process_frame(mock_amp, mock_phase)
        if output:
            print(f"🎯 Dynamic Target Coordinates Isolated: {output}")
