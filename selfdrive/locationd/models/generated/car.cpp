#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                       Code generated with SymPy 1.12                       *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_5102795760562961253) {
   out_5102795760562961253[0] = delta_x[0] + nom_x[0];
   out_5102795760562961253[1] = delta_x[1] + nom_x[1];
   out_5102795760562961253[2] = delta_x[2] + nom_x[2];
   out_5102795760562961253[3] = delta_x[3] + nom_x[3];
   out_5102795760562961253[4] = delta_x[4] + nom_x[4];
   out_5102795760562961253[5] = delta_x[5] + nom_x[5];
   out_5102795760562961253[6] = delta_x[6] + nom_x[6];
   out_5102795760562961253[7] = delta_x[7] + nom_x[7];
   out_5102795760562961253[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_9013605731927444297) {
   out_9013605731927444297[0] = -nom_x[0] + true_x[0];
   out_9013605731927444297[1] = -nom_x[1] + true_x[1];
   out_9013605731927444297[2] = -nom_x[2] + true_x[2];
   out_9013605731927444297[3] = -nom_x[3] + true_x[3];
   out_9013605731927444297[4] = -nom_x[4] + true_x[4];
   out_9013605731927444297[5] = -nom_x[5] + true_x[5];
   out_9013605731927444297[6] = -nom_x[6] + true_x[6];
   out_9013605731927444297[7] = -nom_x[7] + true_x[7];
   out_9013605731927444297[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_5000084352970342056) {
   out_5000084352970342056[0] = 1.0;
   out_5000084352970342056[1] = 0;
   out_5000084352970342056[2] = 0;
   out_5000084352970342056[3] = 0;
   out_5000084352970342056[4] = 0;
   out_5000084352970342056[5] = 0;
   out_5000084352970342056[6] = 0;
   out_5000084352970342056[7] = 0;
   out_5000084352970342056[8] = 0;
   out_5000084352970342056[9] = 0;
   out_5000084352970342056[10] = 1.0;
   out_5000084352970342056[11] = 0;
   out_5000084352970342056[12] = 0;
   out_5000084352970342056[13] = 0;
   out_5000084352970342056[14] = 0;
   out_5000084352970342056[15] = 0;
   out_5000084352970342056[16] = 0;
   out_5000084352970342056[17] = 0;
   out_5000084352970342056[18] = 0;
   out_5000084352970342056[19] = 0;
   out_5000084352970342056[20] = 1.0;
   out_5000084352970342056[21] = 0;
   out_5000084352970342056[22] = 0;
   out_5000084352970342056[23] = 0;
   out_5000084352970342056[24] = 0;
   out_5000084352970342056[25] = 0;
   out_5000084352970342056[26] = 0;
   out_5000084352970342056[27] = 0;
   out_5000084352970342056[28] = 0;
   out_5000084352970342056[29] = 0;
   out_5000084352970342056[30] = 1.0;
   out_5000084352970342056[31] = 0;
   out_5000084352970342056[32] = 0;
   out_5000084352970342056[33] = 0;
   out_5000084352970342056[34] = 0;
   out_5000084352970342056[35] = 0;
   out_5000084352970342056[36] = 0;
   out_5000084352970342056[37] = 0;
   out_5000084352970342056[38] = 0;
   out_5000084352970342056[39] = 0;
   out_5000084352970342056[40] = 1.0;
   out_5000084352970342056[41] = 0;
   out_5000084352970342056[42] = 0;
   out_5000084352970342056[43] = 0;
   out_5000084352970342056[44] = 0;
   out_5000084352970342056[45] = 0;
   out_5000084352970342056[46] = 0;
   out_5000084352970342056[47] = 0;
   out_5000084352970342056[48] = 0;
   out_5000084352970342056[49] = 0;
   out_5000084352970342056[50] = 1.0;
   out_5000084352970342056[51] = 0;
   out_5000084352970342056[52] = 0;
   out_5000084352970342056[53] = 0;
   out_5000084352970342056[54] = 0;
   out_5000084352970342056[55] = 0;
   out_5000084352970342056[56] = 0;
   out_5000084352970342056[57] = 0;
   out_5000084352970342056[58] = 0;
   out_5000084352970342056[59] = 0;
   out_5000084352970342056[60] = 1.0;
   out_5000084352970342056[61] = 0;
   out_5000084352970342056[62] = 0;
   out_5000084352970342056[63] = 0;
   out_5000084352970342056[64] = 0;
   out_5000084352970342056[65] = 0;
   out_5000084352970342056[66] = 0;
   out_5000084352970342056[67] = 0;
   out_5000084352970342056[68] = 0;
   out_5000084352970342056[69] = 0;
   out_5000084352970342056[70] = 1.0;
   out_5000084352970342056[71] = 0;
   out_5000084352970342056[72] = 0;
   out_5000084352970342056[73] = 0;
   out_5000084352970342056[74] = 0;
   out_5000084352970342056[75] = 0;
   out_5000084352970342056[76] = 0;
   out_5000084352970342056[77] = 0;
   out_5000084352970342056[78] = 0;
   out_5000084352970342056[79] = 0;
   out_5000084352970342056[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_5880476250577542540) {
   out_5880476250577542540[0] = state[0];
   out_5880476250577542540[1] = state[1];
   out_5880476250577542540[2] = state[2];
   out_5880476250577542540[3] = state[3];
   out_5880476250577542540[4] = state[4];
   out_5880476250577542540[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8000000000000007*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_5880476250577542540[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_5880476250577542540[7] = state[7];
   out_5880476250577542540[8] = state[8];
}
void F_fun(double *state, double dt, double *out_4931766934280170291) {
   out_4931766934280170291[0] = 1;
   out_4931766934280170291[1] = 0;
   out_4931766934280170291[2] = 0;
   out_4931766934280170291[3] = 0;
   out_4931766934280170291[4] = 0;
   out_4931766934280170291[5] = 0;
   out_4931766934280170291[6] = 0;
   out_4931766934280170291[7] = 0;
   out_4931766934280170291[8] = 0;
   out_4931766934280170291[9] = 0;
   out_4931766934280170291[10] = 1;
   out_4931766934280170291[11] = 0;
   out_4931766934280170291[12] = 0;
   out_4931766934280170291[13] = 0;
   out_4931766934280170291[14] = 0;
   out_4931766934280170291[15] = 0;
   out_4931766934280170291[16] = 0;
   out_4931766934280170291[17] = 0;
   out_4931766934280170291[18] = 0;
   out_4931766934280170291[19] = 0;
   out_4931766934280170291[20] = 1;
   out_4931766934280170291[21] = 0;
   out_4931766934280170291[22] = 0;
   out_4931766934280170291[23] = 0;
   out_4931766934280170291[24] = 0;
   out_4931766934280170291[25] = 0;
   out_4931766934280170291[26] = 0;
   out_4931766934280170291[27] = 0;
   out_4931766934280170291[28] = 0;
   out_4931766934280170291[29] = 0;
   out_4931766934280170291[30] = 1;
   out_4931766934280170291[31] = 0;
   out_4931766934280170291[32] = 0;
   out_4931766934280170291[33] = 0;
   out_4931766934280170291[34] = 0;
   out_4931766934280170291[35] = 0;
   out_4931766934280170291[36] = 0;
   out_4931766934280170291[37] = 0;
   out_4931766934280170291[38] = 0;
   out_4931766934280170291[39] = 0;
   out_4931766934280170291[40] = 1;
   out_4931766934280170291[41] = 0;
   out_4931766934280170291[42] = 0;
   out_4931766934280170291[43] = 0;
   out_4931766934280170291[44] = 0;
   out_4931766934280170291[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_4931766934280170291[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_4931766934280170291[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4931766934280170291[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4931766934280170291[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_4931766934280170291[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_4931766934280170291[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_4931766934280170291[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_4931766934280170291[53] = -9.8000000000000007*dt;
   out_4931766934280170291[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_4931766934280170291[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_4931766934280170291[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4931766934280170291[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4931766934280170291[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_4931766934280170291[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_4931766934280170291[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_4931766934280170291[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4931766934280170291[62] = 0;
   out_4931766934280170291[63] = 0;
   out_4931766934280170291[64] = 0;
   out_4931766934280170291[65] = 0;
   out_4931766934280170291[66] = 0;
   out_4931766934280170291[67] = 0;
   out_4931766934280170291[68] = 0;
   out_4931766934280170291[69] = 0;
   out_4931766934280170291[70] = 1;
   out_4931766934280170291[71] = 0;
   out_4931766934280170291[72] = 0;
   out_4931766934280170291[73] = 0;
   out_4931766934280170291[74] = 0;
   out_4931766934280170291[75] = 0;
   out_4931766934280170291[76] = 0;
   out_4931766934280170291[77] = 0;
   out_4931766934280170291[78] = 0;
   out_4931766934280170291[79] = 0;
   out_4931766934280170291[80] = 1;
}
void h_25(double *state, double *unused, double *out_4714738979208633746) {
   out_4714738979208633746[0] = state[6];
}
void H_25(double *state, double *unused, double *out_6318063418170066029) {
   out_6318063418170066029[0] = 0;
   out_6318063418170066029[1] = 0;
   out_6318063418170066029[2] = 0;
   out_6318063418170066029[3] = 0;
   out_6318063418170066029[4] = 0;
   out_6318063418170066029[5] = 0;
   out_6318063418170066029[6] = 1;
   out_6318063418170066029[7] = 0;
   out_6318063418170066029[8] = 0;
}
void h_24(double *state, double *unused, double *out_1083122230718486604) {
   out_1083122230718486604[0] = state[4];
   out_1083122230718486604[1] = state[5];
}
void H_24(double *state, double *unused, double *out_5847605936126727305) {
   out_5847605936126727305[0] = 0;
   out_5847605936126727305[1] = 0;
   out_5847605936126727305[2] = 0;
   out_5847605936126727305[3] = 0;
   out_5847605936126727305[4] = 1;
   out_5847605936126727305[5] = 0;
   out_5847605936126727305[6] = 0;
   out_5847605936126727305[7] = 0;
   out_5847605936126727305[8] = 0;
   out_5847605936126727305[9] = 0;
   out_5847605936126727305[10] = 0;
   out_5847605936126727305[11] = 0;
   out_5847605936126727305[12] = 0;
   out_5847605936126727305[13] = 0;
   out_5847605936126727305[14] = 1;
   out_5847605936126727305[15] = 0;
   out_5847605936126727305[16] = 0;
   out_5847605936126727305[17] = 0;
}
void h_30(double *state, double *unused, double *out_6915526987730100182) {
   out_6915526987730100182[0] = state[4];
}
void H_30(double *state, double *unused, double *out_6188724471026825959) {
   out_6188724471026825959[0] = 0;
   out_6188724471026825959[1] = 0;
   out_6188724471026825959[2] = 0;
   out_6188724471026825959[3] = 0;
   out_6188724471026825959[4] = 1;
   out_6188724471026825959[5] = 0;
   out_6188724471026825959[6] = 0;
   out_6188724471026825959[7] = 0;
   out_6188724471026825959[8] = 0;
}
void h_26(double *state, double *unused, double *out_5933442894394802070) {
   out_5933442894394802070[0] = state[7];
}
void H_26(double *state, double *unused, double *out_2576560099296009805) {
   out_2576560099296009805[0] = 0;
   out_2576560099296009805[1] = 0;
   out_2576560099296009805[2] = 0;
   out_2576560099296009805[3] = 0;
   out_2576560099296009805[4] = 0;
   out_2576560099296009805[5] = 0;
   out_2576560099296009805[6] = 0;
   out_2576560099296009805[7] = 1;
   out_2576560099296009805[8] = 0;
}
void h_27(double *state, double *unused, double *out_2110333658399936095) {
   out_2110333658399936095[0] = state[3];
}
void H_27(double *state, double *unused, double *out_4013961159226401048) {
   out_4013961159226401048[0] = 0;
   out_4013961159226401048[1] = 0;
   out_4013961159226401048[2] = 0;
   out_4013961159226401048[3] = 1;
   out_4013961159226401048[4] = 0;
   out_4013961159226401048[5] = 0;
   out_4013961159226401048[6] = 0;
   out_4013961159226401048[7] = 0;
   out_4013961159226401048[8] = 0;
}
void h_29(double *state, double *unused, double *out_1953146990048806950) {
   out_1953146990048806950[0] = state[1];
}
void H_29(double *state, double *unused, double *out_6698955815341218143) {
   out_6698955815341218143[0] = 0;
   out_6698955815341218143[1] = 1;
   out_6698955815341218143[2] = 0;
   out_6698955815341218143[3] = 0;
   out_6698955815341218143[4] = 0;
   out_6698955815341218143[5] = 0;
   out_6698955815341218143[6] = 0;
   out_6698955815341218143[7] = 0;
   out_6698955815341218143[8] = 0;
}
void h_28(double *state, double *unused, double *out_702218444869917288) {
   out_702218444869917288[0] = state[0];
}
void H_28(double *state, double *unused, double *out_2781800584712680559) {
   out_2781800584712680559[0] = 1;
   out_2781800584712680559[1] = 0;
   out_2781800584712680559[2] = 0;
   out_2781800584712680559[3] = 0;
   out_2781800584712680559[4] = 0;
   out_2781800584712680559[5] = 0;
   out_2781800584712680559[6] = 0;
   out_2781800584712680559[7] = 0;
   out_2781800584712680559[8] = 0;
}
void h_31(double *state, double *unused, double *out_3166533671545415439) {
   out_3166533671545415439[0] = state[8];
}
void H_31(double *state, double *unused, double *out_6348709380047026457) {
   out_6348709380047026457[0] = 0;
   out_6348709380047026457[1] = 0;
   out_6348709380047026457[2] = 0;
   out_6348709380047026457[3] = 0;
   out_6348709380047026457[4] = 0;
   out_6348709380047026457[5] = 0;
   out_6348709380047026457[6] = 0;
   out_6348709380047026457[7] = 0;
   out_6348709380047026457[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_5102795760562961253) {
  err_fun(nom_x, delta_x, out_5102795760562961253);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_9013605731927444297) {
  inv_err_fun(nom_x, true_x, out_9013605731927444297);
}
void car_H_mod_fun(double *state, double *out_5000084352970342056) {
  H_mod_fun(state, out_5000084352970342056);
}
void car_f_fun(double *state, double dt, double *out_5880476250577542540) {
  f_fun(state,  dt, out_5880476250577542540);
}
void car_F_fun(double *state, double dt, double *out_4931766934280170291) {
  F_fun(state,  dt, out_4931766934280170291);
}
void car_h_25(double *state, double *unused, double *out_4714738979208633746) {
  h_25(state, unused, out_4714738979208633746);
}
void car_H_25(double *state, double *unused, double *out_6318063418170066029) {
  H_25(state, unused, out_6318063418170066029);
}
void car_h_24(double *state, double *unused, double *out_1083122230718486604) {
  h_24(state, unused, out_1083122230718486604);
}
void car_H_24(double *state, double *unused, double *out_5847605936126727305) {
  H_24(state, unused, out_5847605936126727305);
}
void car_h_30(double *state, double *unused, double *out_6915526987730100182) {
  h_30(state, unused, out_6915526987730100182);
}
void car_H_30(double *state, double *unused, double *out_6188724471026825959) {
  H_30(state, unused, out_6188724471026825959);
}
void car_h_26(double *state, double *unused, double *out_5933442894394802070) {
  h_26(state, unused, out_5933442894394802070);
}
void car_H_26(double *state, double *unused, double *out_2576560099296009805) {
  H_26(state, unused, out_2576560099296009805);
}
void car_h_27(double *state, double *unused, double *out_2110333658399936095) {
  h_27(state, unused, out_2110333658399936095);
}
void car_H_27(double *state, double *unused, double *out_4013961159226401048) {
  H_27(state, unused, out_4013961159226401048);
}
void car_h_29(double *state, double *unused, double *out_1953146990048806950) {
  h_29(state, unused, out_1953146990048806950);
}
void car_H_29(double *state, double *unused, double *out_6698955815341218143) {
  H_29(state, unused, out_6698955815341218143);
}
void car_h_28(double *state, double *unused, double *out_702218444869917288) {
  h_28(state, unused, out_702218444869917288);
}
void car_H_28(double *state, double *unused, double *out_2781800584712680559) {
  H_28(state, unused, out_2781800584712680559);
}
void car_h_31(double *state, double *unused, double *out_3166533671545415439) {
  h_31(state, unused, out_3166533671545415439);
}
void car_H_31(double *state, double *unused, double *out_6348709380047026457) {
  H_31(state, unused, out_6348709380047026457);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
