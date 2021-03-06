import numpy as np
import cv2
import copy
import math
import matplotlib.pyplot as plt
import csv

import time
current_milli_time = lambda: int(round(time.time() * 1000))

from pool_simulator import PoolSimulation
from filter.smart_filter import Smart_CAM_Filter
from filter.smart_cvm_filter import Smart_CVM_Filter
from filter.filter_constant_acceleration import CAM_Filter

class Simulation():

    def __init__(self, noise = 1.1, start_velocity = 660, update_time_in_secs = 0.016, name="simulation"):
        self.noise = noise
        self.update_time_in_secs = update_time_in_secs
        self.name = name
        # https://billiards.colostate.edu/faq/speed/typical/
        self.start_velocity = start_velocity

        self.show_video = False

        self.points = list()
        self.mse_list = list()
        self.bank_time_span = list()
        self.filter_predictions = list()
        self.velocities = list()
        self.filter_velocities = list()



    def residual(self, points, ground_truth):
        residuals = list()
        for i in range(0, len(points)):
            point = points[i]
            gt = ground_truth[i]
            residuals.append((point[0] - gt[0], point[1] - gt[1]))
        r = np.array(residuals)
        rx = r[:,0]
        ry = r[:,1]
        mse = (rx ** 2 + ry ** 2).mean()
        return mse

    def create_csv(self, filename="sim.csv"):
        f = open(filename, 'w')

        simulation = PoolSimulation(start_angle=-0.7, start_velocity=self.start_velocity, seconds=self.update_time_in_secs, friction=10.3, noise=self.noise)
        with f:
            writer = csv.writer(f)
            writer.writerow(["POS_X", "POS_Y", "VEL_X", "VEL_Y", "SENSOR_X", "SENSOR_Y", "NEAR_BANK", "TS"])
            while simulation.isBallMoving:
                frame, position, velocity, sensor_pos = simulation.update()
                near_bank = simulation.isBallNearBank
                writer.writerow([*position, *velocity, *sensor_pos, near_bank, self.update_time_in_secs])

    @staticmethod
    def get_noise_from_csv(file):
        f = open(file, 'r')

        x_sum = 0
        y_sum = 0

        with f:
            reader = csv.reader(f)
            rows = [r for r in reader]
            for i in range(1, len(rows)):
                pos_x = float(rows[i][0])
                pos_y = float(rows[i][1])
                sensor_x = float(rows[i][4])
                sensor_y = float(rows[i][5])

                x_dis = math.pow(pos_x - sensor_x, 2)
                y_dis = math.pow(pos_y - sensor_y, 2)

                x_sum += x_dis
                y_sum += y_dis

        noise_x = math.sqrt(x_sum / (len(rows) - 1))
        noise_y = math.sqrt(y_sum / (len(rows) - 1))
        return (noise_x, noise_y)

    @staticmethod
    def get_update_time_from_csv(file):
        f = open(file, 'r')

        with f:
            reader = csv.reader(f)
            rows = [r for r in reader]
            ts = float(rows[1][7])
        return ts


    def run(self, filters, show_video = False, save_prediction = True, show_prediction=0, show_output=True, file=None, show_noised=False, show_gt=True, draw_prediction_path=-1, prediction_path_frame=30):

        if file is None:
            sim = PoolSimulation(start_angle = -0.7, start_velocity = self.start_velocity, seconds=self.update_time_in_secs, friction=10.3, noise=self.noise)
        else:
            self.update_time_in_secs = Simulation.get_update_time_from_csv(file)
            frame, position, velocity, sensor_position, sim = PoolSimulation.update_from_csv(file, 0)

        self.names = list()
        for i in range(0, len(filters)):
            self.names.append(filters[i].name)

        self.points = list()
        self.noised_points = list()

        filter_points = list()
        for i in range(0, len(filters)):
            filter_points.append(list())

        for i in range(0, len(filters)):
            self.filter_velocities.append(list())

        self.filter_predictions = list()
        for i in range(0, len(filters)):
            self.filter_predictions.append(list())


        bank_hits = 0
        bank_start_frame = 0
        near_bank = False

        frame_no = 0
        while sim.isBallMoving:
            start_ms = current_milli_time()
            if file is None:
                frame, position, velocity, sensor_position = sim.update()
            else:
                frame, position, velocity, sensor_position, sim = PoolSimulation.update_from_csv(file, frame_no)
            noised_position = sensor_position

            self.velocities.append(velocity)

            if sim.isBallNearBank:
                if not near_bank:
                    bank_start_frame = frame_no
                near_bank = True
            else:
                if near_bank:
                    self.bank_time_span.append((bank_start_frame, frame_no))
                near_bank = False

            for i, custom_filter in enumerate(filters):
                filter_points[i].append(custom_filter.dofilter(noised_position[0], noised_position[1]))
                self.filter_velocities[i].append(custom_filter.getVelocity())

            self.noised_points.append(noised_position)
            self.points.append(position)

            if save_prediction:
                for i, custom_filter in enumerate(filters):
                    self.filter_predictions[i].append([])
                    pre_pos, pre_var = custom_filter.getPredictions(max_count=61)
                    self.filter_predictions[i][len(self.filter_predictions[i]) - 1] = [pre_pos, pre_var]

            if show_video:
                
                colors = [(255,255,0),(0,255,255), (255,0,255), (55,20,100)]
                for i, filter_point in enumerate(filter_points):
                    if len(filter_point) > 1:
                        last_point = None
                        for point in filter_point:
                            if last_point is not None:
                                cv2.line(frame, (int(last_point[0]),int(last_point[1])), (int(point[0]),int(point[1])), colors[i], 2)
                            last_point = point

                if show_gt:
                    if len(self.points) > 1:
                        last_point = None
                        for point in self.points:
                            if last_point is not None:
                                cv2.line(frame, (int(last_point[0]), int(last_point[1])), (int(point[0]), int(point[1])),
                                        (0, 255, 0), 2)
                            last_point = point
                
                if show_noised:
                    if len(self.noised_points) > 1:
                        last_point = None
                        for point in self.noised_points:
                            if last_point is not None:
                                cv2.line(frame, (int(last_point[0]), int(last_point[1])), (int(point[0]), int(point[1])),
                                        (0, 0, 255), 2)
                            last_point = point


                cv2.circle(frame, (int(noised_position[0]), int(noised_position[1])), 10, (0,0,255), -1)

                if show_prediction > -1 and show_prediction < len(self.filter_predictions):
                    prePos = self.filter_predictions[show_prediction][frame_no][0]
                    preVar = self.filter_predictions[show_prediction][frame_no][1]
                    for i in range(0, len(prePos), 5):
                        cv2.ellipse(frame, (prePos[i][0], prePos[i][1]), (int(4* np.sqrt(preVar[i][0])), int(4*np.sqrt(preVar[i][1]))), 0, 0, 360, (0, 200, 255), 2)

                if draw_prediction_path > -1 and draw_prediction_path < len(self.filter_predictions):
                    if len(self.filter_predictions[0]) > 1:
                        last_point = None
                        for prediction in self.filter_predictions[draw_prediction_path]:
                            point = prediction[0][prediction_path_frame]
                            if last_point is not None:
                                cv2.line(frame, (int(last_point[0]), int(last_point[1])), (int(point[0]), int(point[1])),
                                        (255, 255, 255), 4)
                            last_point = point

                cv2.namedWindow('Pool Simulation', cv2.WINDOW_NORMAL)
                cv2.imshow("Pool Simulation", frame)
                cv2.resizeWindow('Pool Simulation', 1200, 800)
                cv2.moveWindow('Pool Simulation', 0, 0)
                end_ms = current_milli_time()
                execution_time_in_ms = end_ms - start_ms
                cv2.waitKey(max(int(self.update_time_in_secs * 1000) - execution_time_in_ms, 1))
            frame_no += 1

        self.mse_list = list()
        for i in range(0, len(filter_points)):
            self.mse_list.append(10 * np.log10(self.residual(filter_points[i], self.points)))
        self.mse_list.append(10 * np.log10(self.residual(self.noised_points, self.points)))

        if show_output:
            output_string = ""
            for i in range(0, len(filters)):
                output_string += "%s: %fdB " % (filters[i].name, self.mse_list[i])
            output_string += "No Filter: %fdB " % self.mse_list[-1]
            print(output_string)

        return self.mse_list

    def get_predictions(self, filter=0):
        return self.filter_predictions[filter]
    
    def get_mse_of_prediction(self, filter = 0, pre_no = 10, offset=30):
        predictions = self.get_predictions(filter)
        pre_pos = np.array(predictions)[offset:-pre_no, 0, pre_no]
        points = np.array(self.points)[offset+pre_no:]
        return 10 * np.log10(self.residual(pre_pos, points))
    
    def get_prediction_residuals(self, filter = 0, pre_no = 10, offset=30):
        predictions = self.get_predictions(filter)
        pre_pos = np.array(predictions)[offset:-pre_no-1, 0, pre_no-1]
        points = np.array(self.points)[offset+pre_no-1:]

        residuals = list()
        for i in range(0, len(pre_pos)):
            prediction = pre_pos[i]
            gt = points[i]
            distance = math.sqrt((prediction[0] - gt[0])**2 + (prediction[1] - gt[1])**2)
            residuals.append(distance)

        return residuals

    def show_mse_comparison_plot(self, pre_no=30):
        x = np.arange(len(self.mse_list))
        width = 0.35

        pre_mse_list = list()
        for i in range(0, len(self.mse_list) - 1):
            pre_mse_list.append(self.get_mse_of_prediction(i, pre_no=pre_no))
        pre_mse_list.append(0)

        plt.barh(x - width/2, self.mse_list, width, label='MSE of position', zorder=3, color="#ff9a50")
        for i, v in enumerate(self.mse_list):
            plt.text(v - 0.2, i - width/2,  "{:10.2f}dB".format(v), color='black', fontweight='bold', ha='right', va='center')
        plt.barh(x + width/2, pre_mse_list, width, label='MSE prediction %d frames ago' % pre_no, zorder=3, color="#44a9f2")
        for i, v in enumerate(pre_mse_list):
            if v > 0:
                plt.text(v - 0.2, i + width/2,  "{:10.2f}dB".format(v), color='black', fontweight='bold', ha='right', va='center')
        plt.xlabel('MSE in dB')
        plt.yticks(x, [*self.names, "no Filter"])
        plt.gca().invert_yaxis()
        plt.title("Filter Comparison")

        plt.legend()
        plt.grid(axis="x", zorder=0)
        plt.show()

    def show_mse_velocity_comparison_plot(self):

        mse_velocity_list = list()
        for i in range(0, len(self.filter_velocities)):
            mse_velocity_list.append(10 * np.log10(self.residual(self.filter_velocities[i], self.velocities)))

        x = np.arange(len(mse_velocity_list))
        width = 0.35

        plt.bar(x, mse_velocity_list, width, label='MSE of velocity')
        for i, v in enumerate(mse_velocity_list):
            plt.text(i - width / 2, v + 0.5, "{:10.2f}dB".format(v), color='blue', fontweight='bold', ha='center',
                     va='bottom')

        plt.ylabel('mse')
        plt.xticks(x, [*self.names])
        plt.title("Filter Comparison")

        plt.legend()

        plt.show()

    def show_prediction_plot(self, filters=(0), pre_nos=(15, 30, 60), show_bank=False):
        
        for filter_no in filters:
            for pre_no in pre_nos:
                residuals = self.get_prediction_residuals(filter_no, pre_no)
                x = np.arange(0, len(residuals)) + pre_no
                plt.plot(x, residuals, label='Prediction %d frames ago (%s)' % (pre_no, self.names[filter_no]))

        #plt.boxplot([prediction_15_residuals, prediction_30_residuals, prediction_60_residuals], showfliers=False)

        if show_bank:
            for i in range(0, len(self.bank_time_span)):
                plt.axvspan(self.bank_time_span[i][0], self.bank_time_span[i][1], color='red', alpha=0.1)

        #plt.xticks(x, [*self.names, "no Filter"])
        plt.xlabel('frame number')
        plt.ylabel('distance to ground truth')

        #plt.ylim(top=650)
        plt.title("Predictions")
        plt.legend()
        plt.show()

    def show_prediction_boxplot(self, filter=0, pre_nos=(15, 30, 60)):

        residuals = list()
        for pre_no in pre_nos:
            residuals.append(self.get_prediction_residuals(filter, pre_no))

        plt.boxplot(residuals, showfliers=False)

        plt.xticks(range(1, len(residuals) + 1), pre_nos)
        plt.xlabel('prediction # frames ago')
        plt.ylabel('distance to ground truth')
        plt.ylim(top=530)
        plt.title("Predictions")
        plt.legend()
        plt.show()


def show_prediction_boxplot(simulations, filter=0, pre_nos=(15, 30, 60)):

    def set_box_color(bp, color):
        plt.setp(bp['boxes'], color=color)
        plt.setp(bp['whiskers'], color=color)
        plt.setp(bp['caps'], color=color)
        plt.setp(bp['medians'], color=color)

    space_between_groups = 0.8
    space_between_plots = 0.2

    colors = ["#D7191C", "#2C7BB6", "#000000"]

    for i in range(0, len(simulations)):
        residuals = list()
        sim = simulations[i]
        for pre_no in pre_nos:
            residuals.append(sim.get_prediction_residuals(filter, pre_no))
        bplot = plt.boxplot(residuals, positions=np.array(range(len(residuals)))*len(simulations) * space_between_groups+(i * space_between_plots * len(simulations) - ((space_between_plots * len(simulations) * (len(simulations) - 1)) / 2)), showfliers=False)
        set_box_color(bplot, colors[i])
        plt.plot([], c=colors[i], label=sim.name)

    plt.xticks(np.array(range(0, len(pre_nos) * len(simulations), len(simulations))) * space_between_groups, np.array(pre_nos))
    plt.xlabel('prediction # frames ago')
    plt.ylabel('distance to ground truth')
    #plt.ylim(top=530)
    plt.title("Predictions")

    plt.legend()

    plt.grid(axis="y")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":

    # # create simulation files
    # # 9 pixels are 1 cm (table width is 2000 pixel in simulation and 224cm in reallife)
    # testing_noise = [9.0, 27.0, 45.0]
    # # convert m/s to frames/sec: 9 f/s = 1 cm/s (table width is 2000 pixel in simulation and 224cm in reallife)
    # testing_start_velocity = [9 * 80, 9 * 100, 9 * 400]
    # testing_fps = [60, 30, 15]
    
    # for noise in testing_noise:
    #     for vel in testing_start_velocity:
    #         for fps in testing_fps:
    #             sim = Simulation(noise=noise, start_velocity=vel, update_time_in_secs=(1.0 / fps))
    #             sim.create_csv("simulations/sim_" + str(noise) + "_" + str(vel) + "_" + str(fps) + ".csv")

    sim = Simulation()

    boundaries = (PoolSimulation.inset, PoolSimulation.inset + PoolSimulation.table_width, PoolSimulation.inset, PoolSimulation.inset + PoolSimulation.table_height)
    ball_radius = 52

    noise = 9.0
    fps = 1.0 / 60

    normal_cam = CAM_Filter(fps, 200, noise, name="CAM Filter")
    normal_cvm = Smart_CVM_Filter(fps, 2210, noise, name="CVM Filter", smart_prediction=False)

    cam_dynamic = Smart_CAM_Filter(fps, 400, noise, name="dynamic CAM", dynamic_process_noise=40000, smart_prediction=False).setBoundaries(*boundaries).setRadius(ball_radius)
    cvm_dynamic = Smart_CVM_Filter(fps, 300, noise, name="dynamic CVM", dynamic_process_noise=2210, smart_prediction=False).setBoundaries(*boundaries).setRadius(ball_radius)

    smart_cam = Smart_CAM_Filter(fps, 511, noise, name="Smart CAM", dynamic_process_noise=None, smart_prediction=True).setBoundaries(*boundaries).setRadius(ball_radius)
    smart_cvm = Smart_CVM_Filter(fps, 655, noise, name="Smart CVM").setBoundaries(*boundaries).setRadius(ball_radius)
    
    smart_dyn_cvm = Smart_CVM_Filter(fps, 350, noise, name="dynamic smart CVM", dynamic_process_noise=860,).setBoundaries(*boundaries).setRadius(ball_radius)
    smart_dyn_cam = Smart_CAM_Filter(fps, 350, noise, name="dynamic smart CAM", dynamic_process_noise=860, smart_prediction=True).setBoundaries(*boundaries).setRadius(ball_radius)

    filters = [smart_cvm]
    sim.run(filters, show_video=True, show_gt=False, show_noised=True, show_prediction=-1, draw_prediction_path=0, save_prediction=True, file="simulations/sim_9.0_900_60.csv")
    #sim.show_mse_velocity_comparison_plot()
    sim.show_mse_comparison_plot(pre_no=30)
    #sim.show_prediction_boxplot(filter=2,pre_nos=(15, 30, 60))
    #sim.show_prediction_plot(filters=(1, 2), pre_nos=[30], show_bank=True)

    #show_prediction_boxplot([sim, sim2, sim3], 2)